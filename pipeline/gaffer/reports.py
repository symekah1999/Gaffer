"""Weekly results: backtests, accuracy and per-team reports comparing predictions with reality."""
import numpy as np


def truncate_to_gw(boot, fixtures, hist, gw):
    """Inputs as they looked just before gameweek `gw` (results and histories before it only).
    Injury news from that time is not available, so everyone is treated as available."""
    events = [{**e, "is_next": e["id"] == gw, "is_current": e["id"] == gw - 1, "finished": e["id"] < gw}
              for e in boot["events"]]
    fx = [f if (f.get("event") or 99) < gw else {**f, "team_h_score": None, "team_a_score": None, "finished": False}
          for f in fixtures]
    h2, price, club = {}, {}, {}
    for pid, s in hist.items():
        rows = s.get("history") or []
        h2[pid] = {"history": [r for r in rows if (r.get("round") or 99) < gw], "history_past": s.get("history_past")}
        row = next((r for r in rows if r.get("round") == gw), None)
        if row and row.get("value"):
            price[pid] = row["value"]
        if row and row.get("team_id") is not None and row["team_id"] == row["team_id"]:   # archive data only
            club[pid] = int(row["team_id"])
    els = [{**e, "status": "a", "chance_of_playing_next_round": None, "news": "",
            "now_cost": price.get(e["id"], e["now_cost"]), "team": club.get(e["id"], e["team"])} for e in boot["elements"]]
    return {**boot, "events": events, "elements": els}, fx, h2


def _top10(score, results):
    if not score:
        return None
    top = sorted(score, key=lambda p: -score[p])[:10]
    return float(np.mean([results.get(p, (0, 0))[0] for p in top]))


def accuracy(preds, results, price=None, form=None):
    """preds {pid: xp}; results {pid: (points, minutes)}; price/form {pid: value} give rival top-10 picks."""
    rows = [(xp, results[p][0]) for p, xp in preds.items() if p in results and (results[p][1] > 0 or xp >= 2)]
    if len(rows) < 20:
        return None
    x, y = np.array(rows, float).T
    top = sorted(preds, key=lambda p: -preds[p])[:10]
    played = [r[0] for r in results.values() if r[1] > 0]
    return dict(n=len(rows), mae=float(np.mean(np.abs(x - y))), rmse=float(np.sqrt(np.mean((x - y) ** 2))),
                corr=float(np.corrcoef(x, y)[0, 1]),
                top10_avg=float(np.mean([results.get(p, (0, 0))[0] for p in top])),
                field_avg=float(np.mean(played)) if played else None,
                price_top10_avg=_top10(price, results), form_top10_avg=_top10(form, results))


def best_lineup(ids, xp, pos):
    by = {p: sorted([i for i in ids if pos.get(i) == p], key=lambda i: -xp.get(i, 0)) for p in (1, 2, 3, 4)}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3 and by[1] and len(by[2]) >= d and len(by[3]) >= m and len(by[4]) >= f:
                xi = by[1][:1] + by[2][:d] + by[3][:m] + by[4][:f]
                s = sum(xp.get(i, 0) for i in xi)
                if best is None or s > best[0]:
                    best = (s, xi)
    if not best:
        return [], None
    xi = best[1]
    return xi, max(xi, key=lambda i: xp.get(i, 0))


def team_report(gw, kind, picks_resp, hist_row, entry, preds, results, meta):
    """meta {pid: dict(name, team, pos)}."""
    picks = picks_resp["picks"]
    pts = {p: results.get(p, (0, 0))[0] for p in [k["element"] for k in picks]}
    mins = {p: results.get(p, (0, 0))[1] for p in pts}
    xp = {p: float(preds.get(p, 0)) for p in pts}
    pos = {p: meta.get(p, {}).get("pos") for p in pts}
    ids = list(pts)
    predicted = sum(xp[k["element"]] * k["multiplier"] for k in picks)
    lineup_actual = sum(pts[k["element"]] * k["multiplier"] for k in picks)
    gx, gc = best_lineup(ids, xp, pos)
    cap = next((k for k in picks if k.get("is_captain")), None)
    def who(i, mult=None):
        m = meta.get(i, {})
        d = dict(id=i, name=m.get("name", str(i)), team=m.get("team", ""), xp=round(xp.get(i, 0), 2), pts=pts.get(i, 0))
        if mult is not None:
            d["mult"] = mult
        return d
    players = [dict(**who(k["element"], k["multiplier"]), pos=pos[k["element"]], minutes=mins[k["element"]],
                    is_captain=bool(k.get("is_captain")), slot=k.get("position")) for k in picks]
    h = hist_row or {}
    return dict(
        gw=gw, kind=kind, chip=picks_resp.get("active_chip"),
        team_name=entry.get("name"), manager=f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip(),
        points=h.get("points", lineup_actual), transfer_cost=h.get("event_transfers_cost", 0),
        transfers=h.get("event_transfers", 0), gw_rank=h.get("rank"), overall_rank=h.get("overall_rank"),
        total_points=h.get("total_points"), bench_points=h.get("points_on_bench"),
        predicted=round(predicted, 1), lineup_actual=lineup_actual,
        gaffer_pred=round(sum(xp[i] for i in gx) + (xp[gc] if gc else 0), 1),
        gaffer_actual=sum(pts[i] for i in gx) + (pts[gc] if gc else 0),
        gaffer_xi=gx, captain=who(cap["element"], cap["multiplier"]) if cap else None,
        gaffer_captain=who(gc) if gc else None, players=players)
