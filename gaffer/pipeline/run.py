"""Fetch FPL data, build projections, publish weekly results. Writes everything to Neon.

Run:  DATABASE_URL=... python -m pipeline.run        (FPL_MOCK=1 for simulated data)
Optional: TRACK_TEAM_IDS="1234567,7654321" to always publish reports for those FPL teams.
"""
import asyncio, json, os, time
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from .gaffer import model, reports

SCHEMA = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text()
KEEP_SNAPSHOTS = 10
BACKFILL_PER_RUN = int(os.getenv("BACKFILL_PER_RUN", "12"))


def dumps(o):
    return json.dumps(o, default=lambda x: x.item() if hasattr(x, "item") else str(x))


def J(o):
    return Jsonb(o, dumps=dumps)


def log(*a):
    print(*a, flush=True)


def upsert_predictions(conn, gw, df, kind):
    col = f"xp_{gw}"
    rows = [(gw, int(i), float(x), float(pp), float(pr), kind)
            for i, x, pp, pr in zip(df.id, df[col], df.p_play, df.price)]
    with conn.cursor() as cur:
        cur.executemany("""insert into predictions (gw, player_id, xp, p_play, price, kind, made_at)
                           values (%s, %s, %s, %s, %s, %s, now())
                           on conflict (gw, player_id) do update set xp = excluded.xp, p_play = excluded.p_play,
                             price = excluded.price, kind = excluded.kind, made_at = now()""", rows)


async def main_async():
    url = os.environ["DATABASE_URL"]
    mock = os.getenv("FPL_MOCK") == "1"
    if mock:
        from .gaffer.mock_data import MockClient; client = MockClient()
    else:
        from .gaffer.fpl_client import FPLClient; client = FPLClient()
    t0 = time.time()
    log("Fetching FPL data", "(mock)" if mock else "")
    boot, fixtures = await client.bootstrap(), await client.fixtures()
    ids = [e["id"] for e in boot["elements"] if e.get("status") not in ("u", "n")]
    def prog(done, total):
        if done % 100 == 0 or done == total:
            log(f"  histories {done}/{total}")
    hist = await client.histories(ids, prog)

    log("Building projections")
    df, grid, meta = model.build_projections(boot, fixtures, hist, horizon=8)
    first = {pid: ((h.get("history") or [{}])[0].get("value")) for pid, h in hist.items()}
    df["start_price"] = [(first.get(i) or p * 10) / 10 for i, p in zip(df.id, df.price)]
    nxt = next(e for e in boot["events"] if e["id"] == meta["next_gw"])
    meta["next_deadline"] = nxt.get("deadline_time")
    ev = next((e for e in boot["events"] if e.get("is_current")), None) or \
         next((e for e in boot["events"] if e.get("is_previous")), None)
    players = df.astype(object).where(df.notna(), None).to_dict("records")
    el_meta = {e["id"]: dict(name=e["web_name"], team=next(t["short_name"] for t in boot["teams"] if t["id"] == e["team"]),
                             pos=e["element_type"]) for e in boot["elements"]}
    finished = sorted(e["id"] for e in boot["events"] if e.get("finished"))
    source = "mock" if mock else "live"

    with psycopg.connect(url) as conn:
        conn.execute(SCHEMA)
        conn.execute("insert into snapshots (next_gw, picks_gw, source, gws, players, fixtures, meta) "
                     "values (%s, %s, %s, %s, %s, %s, %s)",
                     (meta["next_gw"], ev["id"] if ev else None, source, J(meta["gws"]), J(players), J(grid), J(meta)))
        conn.execute(f"delete from snapshots where id not in (select id from snapshots order by id desc limit {KEEP_SNAPSHOTS})")
        upsert_predictions(conn, meta["next_gw"], df, "live")      # frozen once the deadline passes
        conn.commit()
        log(f"Saved snapshot and GW{meta['next_gw']} predictions")

        # ---- backfill reconstructed predictions for finished gameweeks
        have = {r[0] for r in conn.execute("select distinct gw from predictions")}
        for gw in [g for g in finished if g not in have][:BACKFILL_PER_RUN]:
            b, f, h = reports.truncate_to_gw(boot, fixtures, hist, gw)
            dfg, _, _ = model.build_projections(b, f, h, horizon=1)
            upsert_predictions(conn, gw, dfg, "backtest")
            conn.commit()
            log(f"  backtest GW{gw}")

        # ---- actual points
        have_res = {r[0] for r in conn.execute("select distinct gw from results")}
        recent = set(finished[-2:])
        for gw in finished:
            if gw in have_res and gw not in recent:
                continue
            live = await client.event_live(gw)
            rows = [(gw, e["id"], int(e["stats"].get("total_points") or 0), int(e["stats"].get("minutes") or 0))
                    for e in live.get("elements", [])]
            with conn.cursor() as cur:
                cur.executemany("""insert into results (gw, player_id, points, minutes) values (%s, %s, %s, %s)
                                   on conflict (gw, player_id) do update set points = excluded.points, minutes = excluded.minutes""", rows)
            conn.commit()

        # ---- accuracy per gameweek
        preds_by_gw, kind_by_gw = {}, {}
        for gw, pid, xp, kind in conn.execute("select gw, player_id, xp, kind from predictions where gw = any(%s)", (finished,)):
            preds_by_gw.setdefault(gw, {})[pid] = xp
            kind_by_gw[gw] = kind
        res_by_gw = {}
        for gw, pid, pts, mins in conn.execute("select gw, player_id, points, minutes from results"):
            res_by_gw.setdefault(gw, {})[pid] = (pts, mins)
        for gw, preds in preds_by_gw.items():
            a = reports.accuracy(preds, res_by_gw.get(gw, {}))
            if a:
                conn.execute("""insert into gw_accuracy (gw, kind, n, mae, rmse, corr, top10_avg, field_avg, computed_at)
                                values (%(gw)s, %(kind)s, %(n)s, %(mae)s, %(rmse)s, %(corr)s, %(top10_avg)s, %(field_avg)s, now())
                                on conflict (gw) do update set kind = excluded.kind, n = excluded.n, mae = excluded.mae,
                                  rmse = excluded.rmse, corr = excluded.corr, top10_avg = excluded.top10_avg,
                                  field_avg = excluded.field_avg, computed_at = now()""", dict(gw=gw, kind=kind_by_gw[gw], **a))
        conn.commit()

        # ---- weekly team reports
        tracked = {r[0] for r in conn.execute("select team_id from user_settings where team_id is not null")}
        tracked |= {int(x) for x in os.getenv("TRACK_TEAM_IDS", "").replace(" ", "").split(",") if x.isdigit()}
        if mock and not tracked:
            tracked = {1234567}
        for tid in sorted(tracked):
            try:
                entry, ehist = await client.entry(tid), await client.entry_history(tid)
            except Exception as e:
                log(f"  team {tid}: skipped ({e.__class__.__name__})"); continue
            hrows = {r["event"]: r for r in ehist.get("current", [])}
            done = {r[0] for r in conn.execute("select gw from team_reports where team_id = %s", (tid,))}
            n = 0
            for gw in finished:
                if gw not in hrows or gw not in preds_by_gw or (gw in done and gw not in recent):
                    continue
                try:
                    picks = await client.entry_picks(tid, gw)
                except Exception:
                    continue
                rep = reports.team_report(gw, kind_by_gw[gw], picks, hrows[gw], entry, preds_by_gw[gw],
                                          res_by_gw.get(gw, {}), el_meta)
                conn.execute("""insert into team_reports (team_id, gw, data) values (%s, %s, %s)
                                on conflict (team_id, gw) do update set data = excluded.data, created_at = now()""",
                             (tid, gw, J(rep)))
                n += 1
            conn.commit()
            log(f"  team {tid}: {n} weekly reports published")

    ml = meta["ml"]
    log(f"Done in {time.time() - t0:.0f}s. GW{meta['next_gw']}, {len(players)} players. "
        f"ML {'on, weight ' + str(round(ml['weight'], 2)) if ml.get('enabled') else 'off: ' + ml.get('reason', '')}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
