"""Season simulation: let Gaffer manage an FPL team through a past season using only information available
before each deadline, and compare its weekly average with simpler strategies.

    python -m pipeline.backtest            # test season 2025-26, trained on the three seasons before it

Writes pipeline/backtest_results.json, which the data job publishes on the Model page.
Rules simulated: £100m start, 1 free transfer a week (up to 5 banked), -4 per extra transfer, captain
doubled, max 3 per club. Simplifications: no chips, no auto-subs, players sell at their current price.
"""
import json, os, pickle, sys, time
from pathlib import Path
import numpy as np
import importlib.util
from .gaffer import history, model, reports

TEST, TRAIN = "2025-26", ["2022-23", "2023-24", "2024-25"]
HORIZON, OUT = 5, Path(__file__).with_name("backtest_results.json")
CACHE = Path(os.getenv("HISTORY_CACHE", "/tmp/gaffer-history")) / f"preds-{TEST}.pkl"

spec = importlib.util.spec_from_file_location("api_main", Path(__file__).resolve().parent.parent / "api" / "main.py")
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)


def log(*a):
    print(*a, flush=True)


def predictions():
    """Per gameweek: every player's statistical and ML projection for that GW and the next four."""
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    extra = history.load_history(TRAIN, log=log)
    boot, fixtures, hist, actual, official = history.load_season(TEST, TRAIN[-1])
    out = {}
    for gw in range(1, 39):
        t = time.time()
        b, f, h = reports.truncate_to_gw(boot, fixtures, hist, gw)
        df, _, meta = model.build_projections(b, f, h, horizon=HORIZON, extra=extra, evaluate=False)
        gws = meta["gws"]
        out[gw] = dict(gws=gws, players=[dict(id=int(r.id), pos=int(r.pos), team=int(r.team), price=float(r.price),
                                              h={g: float(getattr(r, f"h_{g}")) for g in gws},
                                              m={g: (None if getattr(r, f"m_{g}") is None or np.isnan(getattr(r, f"m_{g}")) else float(getattr(r, f"m_{g}"))) for g in gws})
                                         for r in df.itertuples()])
        log(f"  GW{gw}: projections in {time.time() - t:.0f}s")
    form = {}
    for pid, s in hist.items():
        rows = s["history"]
        for gw in range(1, 39):
            prev = [r["total_points"] for r in rows if r["round"] < gw][-5:]
            form[(pid, gw)] = float(np.mean(prev)) if prev else 0.0
    data = dict(preds=out, actual=actual, official=official, form=form)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(data))
    return data


def engine_xp(name, p, gw, gws, data):
    if name.startswith("gaffer"):
        w = float(name.split(":")[1])
        return {g: (w * p["m"][g] + (1 - w) * p["h"][g]) if p["m"][g] is not None else p["h"][g] for g in gws}
    if name == "form":
        v = data["form"].get((p["id"], gw), 0.0); return {g: v for g in gws}
    if name == "fpl_xp":
        v = data["official"].get(gw, {}).get(p["id"]) or 0.0; return {g: float(v) for g in gws}
    raise ValueError(name)


def accuracy(name, data):
    """How well one engine predicts a single gameweek: correlation and top-10 points."""
    corrs, top, field = [], [], []
    for gw, d in data["preds"].items():
        act = data["actual"].get(gw, {})
        xs = {p["id"]: engine_xp(name, p, gw, d["gws"], data)[gw] for p in d["players"]}
        pairs = [(x, act[i][0]) for i, x in xs.items() if i in act and (act[i][1] > 0 or x >= 2)]
        if len(pairs) > 20:
            a = np.array(pairs).T
            if a[0].std() > 0:                      # GW1 has no form / no data for some engines
                corrs.append(np.corrcoef(a[0], a[1])[0, 1])
        best = sorted(xs, key=lambda i: -xs[i])[:10]
        top.append(np.mean([act.get(i, (0, 0))[0] for i in best]))
        field.append(np.mean([v[0] for v in act.values() if v[1] > 0]))
    return dict(corr=float(np.mean(corrs)), top10=float(np.mean(top)), field=float(np.mean(field)))


def simulate(name, data, ft_value=0.0, max_transfers=2, planner=False):
    """Manage a team for the whole season with one engine's predictions. planner=True uses the app's
    week-by-week planner (rolls free transfers, takes hits only when worth it); otherwise the best single move."""
    squad, bank, ft, weeks = None, 0.0, 1, []
    for gw in range(1, 39):
        d = data["preds"][gw]; gws = d["gws"][:HORIZON]
        players = []
        for p in d["players"]:
            row = dict(id=p["id"], pos=p["pos"], team=p["team"], price=p["price"])
            row.update({f"xp_{g}": v for g, v in engine_xp(name, p, gw, gws, data).items()})
            players.append(row)
        price = {p["id"]: p["price"] for p in players}
        if squad is None:
            res = api.optimise(players, gws, budget=100.0, time_limit=10)
            bank, k, hits = round(100.0 - res["cost"], 1), 0, 0
        elif planner:
            cur = {i: price[i] for i in squad}
            res, plan_weeks, _, _ = api.plan_multi(players, gws, current=cur, bank=bank, free_transfers=ft, time_limit=15)
            k, hits = len(res["transfers_in"]), plan_weeks[0]["hits"]
            bank = round(bank + sum(cur[i] for i in res["transfers_out"]) - sum(price[i] for i in res["transfers_in"]), 1)
            ft = min(5, max(ft - k, 0) + 1)
        else:
            cur = {i: price[i] for i in squad}
            best = None
            for k in range(0, max_transfers + 1):
                r = api.optimise(players, gws, current=cur, bank=bank, free_transfers=ft, max_transfers=k, time_limit=6)
                ft_next = min(5, max(ft - len(r["transfers_in"]), 0) + 1)
                score = r["net_total"] + ft_value * ft_next
                if best is None or score > best[0] + 1e-9:
                    best = (score, r)
            res = best[1]
            k = len(res["transfers_in"]); hits = max(0, k - ft)
            bank = round(bank + sum(cur[i] for i in res["transfers_out"]) - sum(price[i] for i in res["transfers_in"]), 1)
            ft = min(5, max(ft - k, 0) + 1)
        squad = res["squad"]
        lu = res["lineups"][0]
        act = data["actual"].get(gw, {})
        pts = sum(act.get(i, (0, 0))[0] for i in lu["xi"]) + act.get(lu["captain"], (0, 0))[0] - 4 * hits
        weeks.append(dict(gw=gw, points=int(pts), transfers=k, hits=hits))
    tot = sum(w["points"] for w in weeks)
    return dict(total=tot, average=tot / len(weeks), hits=sum(w["hits"] for w in weeks), weeks=weeks)


def main():
    t0 = time.time()
    data = predictions()
    log(f"Predictions ready ({time.time() - t0:.0f}s)")
    engines = {"gaffer:0.0": "Gaffer statistical model only", "gaffer:0.3": "Gaffer, 30% machine learning",
               "gaffer:0.6": "Gaffer, 60% machine learning", "gaffer:1.0": "Machine learning only",
               "form": "Form (average of last 5 games)", "fpl_xp": "FPL's official expected points"}
    only = sys.argv[1:] or list(engines)
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    res.update(season=TEST, trained_on=TRAIN, rules=__doc__.split("Rules simulated: ")[1].strip())
    res.setdefault("engines", {})
    if only == ["--accuracy"]:                      # refresh accuracy numbers without re-simulating
        for e, r in res["engines"].items():
            r.update(accuracy(e.replace("+plan", ""), data))
        OUT.write_text(json.dumps(res, indent=1)); log("accuracy refreshed"); return
    for e in only:
        if e.endswith("+plan"):
            base = e[:-5]
            r = dict(**accuracy(base, data), **simulate(base, data, planner=True))
            r["label"] = engines[base] + ", week-by-week planner"
        else:
            r = dict(**accuracy(e, data), **simulate(e, data)); r["label"] = engines[e]
        res["engines"][e] = r
        log(f"{r['label']}: {r['average']:.1f} pts/week ({r['total']} total, {r['hits']} hits), corr {r['corr']:.3f}, top10 {r['top10']:.2f}")
        OUT.write_text(json.dumps(res, indent=1))
    log(f"Done in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
