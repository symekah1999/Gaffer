"""Expected-points engine: a fixture-aware Poisson model blended with a boosted-tree correction."""
from __future__ import annotations
import math
from collections import defaultdict
import numpy as np
import pandas as pd
from .ratings import compute_ratings, team_xg, baselines
from . import ml

POS_NAME = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
GOAL_PTS = {1: 6, 2: 6, 3: 5, 4: 4}
CS_PTS = {1: 4, 2: 4, 3: 1, 4: 0}
DC_THRESHOLD = {2: 10, 3: 12, 4: 12}
DEFAULT = {
    1: dict(g=0.00, a=0.02, bonus=0.20, cards=0.10, saves=2.8, dc=0.0),
    2: dict(g=0.05, a=0.07, bonus=0.20, cards=0.20, saves=0.0, dc=0.40),
    3: dict(g=0.12, a=0.12, bonus=0.22, cards=0.20, saves=0.0, dc=0.20),
    4: dict(g=0.30, a=0.10, bonus=0.30, cards=0.18, saves=0.0, dc=0.06),
}
NUM = ["minutes", "goals_scored", "assists", "expected_goals", "expected_assists", "bonus", "saves",
       "yellow_cards", "red_cards", "defensive_contribution", "total_points"]


def pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def e_floor(lam, d, kmax=16):
    """E[floor(X/d)] for X ~ Poisson(lam)."""
    return sum((k // d) * pmf(k, lam) for k in range(kmax + 1))


def shrunk(obs, mins, prior_rate, prior_mins):
    return (obs + prior_rate * prior_mins / 90.0) / (mins + prior_mins) * 90.0


def blend(goals, xg):
    goals, xg = np.nan_to_num(np.asarray(goals, float)), np.asarray(xg, float)
    return np.where(np.isnan(xg), goals, 0.65 * xg + 0.35 * goals)


def to_frame(summary):
    df = pd.DataFrame(summary.get("history") or [])
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    return df


def position_priors(frames, pos_of):
    acc = {p: defaultdict(float) for p in POS_NAME}
    has_dc = False
    for pid, df in frames.items():
        if df.empty or pid not in pos_of:
            continue
        p, a, m = pos_of[pid], acc[pos_of[pid]], df["minutes"].fillna(0)
        a["mins"] += m.sum()
        a["g"] += blend(df["goals_scored"].values, df["expected_goals"].values).sum()
        a["a"] += blend(df["assists"].values, df["expected_assists"].values).sum()
        a["bonus"] += df["bonus"].fillna(0).sum()
        a["cards"] += (df["yellow_cards"].fillna(0) + 3 * df["red_cards"].fillna(0)).sum()
        a["saves"] += df["saves"].fillna(0).sum()
        if df["defensive_contribution"].notna().any():
            has_dc = True
            thr = DC_THRESHOLD.get(p)
            if thr:
                ap = df[m >= 45]
                a["dc_n"] += len(ap)
                a["dc_hit"] += float((ap["defensive_contribution"].fillna(0) >= thr).sum())
    priors = {}
    for p in POS_NAME:
        d, a = dict(DEFAULT[p]), acc[p]
        if a["mins"] >= 2500:
            for k in ("g", "a", "bonus", "cards", "saves"):
                d[k] = a[k] / a["mins"] * 90
        if a["dc_n"] >= 100:
            d["dc"] = a["dc_hit"] / a["dc_n"]
        priors[p] = d
    return priors, has_dc


def player_rates(df, past, pos, prior, has_dc):
    last = next((r for r in reversed(past or []) if (r.get("minutes") or 0) >= 600), None)
    sp = dict(prior)
    prior_min = 20.0
    if last:
        lm = float(last["minutes"])
        f = lambda k: float(last.get(k) or 0)
        xg, xa = last.get("expected_goals"), last.get("expected_assists")
        g = 0.65 * float(xg) + 0.35 * f("goals_scored") if xg not in (None, "") else f("goals_scored")
        a = 0.65 * float(xa) + 0.35 * f("assists") if xa not in (None, "") else f("assists")
        obs = dict(g=g, a=a, bonus=f("bonus"), cards=f("yellow_cards") + 3 * f("red_cards"), saves=f("saves"))
        for k, v in obs.items():
            sp[k] = shrunk(v, lm, prior[k], 900)
        prior_min = lm / 38.0
    rates, n = dict(sp), len(df)
    p60_prior, pany_prior = min(1, max(0, (prior_min - 10) / 75)), min(1, prior_min / 45)
    if n:
        w = 0.5 ** (np.arange(n)[::-1] / 6.0)
        m = df["minutes"].fillna(0).values
        wm = (w * m).sum()
        cur = dict(
            g=(w * blend(df["goals_scored"].values, df["expected_goals"].values)).sum(),
            a=(w * blend(df["assists"].values, df["expected_assists"].values)).sum(),
            bonus=(w * df["bonus"].fillna(0).values).sum(),
            cards=(w * (df["yellow_cards"].fillna(0) + 3 * df["red_cards"].fillna(0)).values).sum(),
            saves=(w * df["saves"].fillna(0).values).sum(),
        )
        for k, v in cur.items():
            rates[k] = shrunk(v, wm, sp[k], 540)
        ap = m >= 45
        if has_dc and pos in DC_THRESHOLD:
            dcv = np.nan_to_num(df["defensive_contribution"].values.astype(float))
            hit = (dcv >= DC_THRESHOLD[pos]) & ap
            rates["dc"] = (np.sum(w * hit) + 4 * prior["dc"]) / (np.sum(w * ap) + 4)
        t = df.tail(6)
        wt = 0.5 ** (np.arange(len(t))[::-1] / 3.0)
        tm = t["minutes"].fillna(0).values
        W = wt.sum() + 2
        rates["e_min"] = ((wt * tm).sum() + 2 * prior_min) / W
        rates["p60"] = ((wt * (tm >= 60)).sum() + 2 * p60_prior) / W
        rates["pany"] = ((wt * (tm > 0)).sum() + 2 * pany_prior) / W
    else:
        rates.update(e_min=prior_min, p60=p60_prior, pany=pany_prior)
    rates["pany"] = max(rates["pany"], rates["p60"])
    if not has_dc:
        rates["dc"] = 0.0
    rates["n"] = n
    return rates


def availability(el, k):
    status, c = el.get("status", "a"), el.get("chance_of_playing_next_round")
    if c is None:
        c = {"a": 100, "d": 50}.get(status, 0)
    c /= 100.0
    if status == "a" and c >= 1:
        return 1.0
    rec = {"d": 0.30, "i": 0.12, "s": 0.35}.get(status, 0.25)
    return float(min(1.0, c + (1 - c) * min(1.0, rec * k)))


def fixture_points(pos, r, xgf, xga, base_att, base_def, dom_base):
    mf, p60, pany = r["e_min"] / 90.0, r["p60"], r["pany"]
    matt = float(np.clip(xgf / base_att, 0.5, 2.0))
    dom = float(np.clip(math.sqrt(xgf / max(xga, 0.05)) / dom_base, 0.6, 1.6))
    bd = dict(
        appearance=2 * p60 + (pany - p60),
        goals=r["g"] * mf * matt * GOAL_PTS[pos],
        assists=r["a"] * mf * matt * 3,
        clean_sheet=math.exp(-xga) * p60 * CS_PTS[pos],
        conceded=-e_floor(xga, 2) * p60 if pos in (1, 2) else 0.0,
        saves=e_floor(r["saves"] * mf * float(np.clip(xga / base_def, 0.5, 2.0)), 3) if pos == 1 else 0.0,
        bonus=r["bonus"] * mf * dom,
        cards=-r["cards"] * mf,
        defensive=2 * r["dc"] * p60 if pos in DC_THRESHOLD else 0.0,
    )
    return sum(bd.values()), bd


def next_gameweek(events):
    for e in events:
        if e.get("is_next"):
            return e["id"]
    raise ValueError("No upcoming gameweek: the season looks finished.")


ML_WEIGHT = 0.3   # tuned by the season simulation, see pipeline/backtest.py


def build_projections(bootstrap, fixtures, histories, horizon=8, progress=None, extra=None, evaluate=True):
    teams, events = bootstrap["teams"], bootstrap["events"]
    elements = [e for e in bootstrap["elements"] if e.get("element_type") in POS_NAME]
    team_short = {t["id"]: t["short_name"] for t in teams}
    next_gw = next_gameweek(events)
    gws = [g for g in range(next_gw, min(next_gw + horizon, 39))]
    ratings, H, A = compute_ratings(teams, fixtures, next_gw)

    team_fx = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        if f.get("event") in gws:
            for team, opp, home in ((f["team_h"], f["team_a"], True), (f["team_a"], f["team_h"], False)):
                xgf, xga = team_xg(ratings, H, A, team, opp, home)
                team_fx[team][f["event"]].append(dict(opp=team_short[opp], home=home, xgf=xgf, xga=xga))

    pos_of = {e["id"]: e["element_type"] for e in elements}
    frames = {pid: to_frame(s) for pid, s in histories.items() if pid in pos_of}
    priors, has_dc = position_priors(frames, pos_of)
    empty = to_frame({})

    heur, bds, rates_of, upcoming = {}, {}, {}, []
    for e in elements:
        pid, pos, tid = e["id"], e["element_type"], e["team"]
        r = player_rates(frames.get(pid, empty), (histories.get(pid) or {}).get("history_past"), pos, priors[pos], has_dc)
        rates_of[pid] = r
        base_att, base_def, dom_base = baselines(ratings, H, A, tid)
        heur[pid], bds[pid] = {}, {}
        for k, gw in enumerate(gws):
            tot, bd_sum = 0.0, defaultdict(float)
            for fx in team_fx[tid].get(gw, []):
                pts, bd = fixture_points(pos, r, fx["xgf"], fx["xga"], base_att, base_def, dom_base)
                tot += pts
                for kk, v in bd.items():
                    bd_sum[kk] += v
                upcoming.append(dict(player=pid, gw=gw, pos=pos, value=e["now_cost"] / 10,
                                     was_home=1 if fx["home"] else 0, xgf=fx["xgf"], xga=fx["xga"]))
            av = availability(e, k)
            heur[pid][gw] = tot * av
            if k == 0:
                bds[pid] = {kk: round(v * av, 2) for kk, v in bd_sum.items()}

    ml_pred, ml_hauls, ml_meta = ml.run_ml(elements, teams, fixtures, histories, upcoming, extra=extra, evaluate=evaluate)
    rounds = ml_meta.get("rounds", 0)
    w_ml = 0.0
    if ml_meta.get("enabled"):
        if ml_meta.get("history_rows"):
            # Trained on past seasons. 30% scored the most points in the 2025-26 season simulation
            # (pipeline/backtest.py); more ML predicted slightly better but chased hits and scored less.
            skill = ml_meta.get("skill", ml_meta.get("season_test", {}).get("skill", 0))
            w_ml = ML_WEIGHT if skill > 0 else 0.0
        elif ml_meta.get("skill", 0) > 0:
            w_ml = float(np.clip(0.05 * (rounds - 3), 0.0, 0.3))
    ml_meta["weight"] = w_ml

    rows = []
    for e in elements:
        pid, tid = e["id"], e["team"]
        row = dict(
            id=pid, name=e["web_name"], team=tid, team_short=team_short[tid], pos=e["element_type"],
            pos_name=POS_NAME[e["element_type"]], price=e["now_cost"] / 10, status=e.get("status", "a"),
            news=e.get("news", ""), chance=e.get("chance_of_playing_next_round"),
            selected=float(e.get("selected_by_percent") or 0), form=float(e.get("form") or 0),
            total_points=e.get("total_points", 0), minutes=e.get("minutes", 0),
            p_play=round(availability(e, 0), 2), e_min=round(rates_of[pid]["e_min"], 1),
            fixtures={}, bd=bds.get(pid, {}), haul={},
        )
        tot = 0.0
        for k, gw in enumerate(gws):
            h = heur[pid][gw]
            v = h
            if w_ml and (pid, gw) in ml_pred:
                v = w_ml * ml_pred[(pid, gw)] * availability(e, k) + (1 - w_ml) * h
            row[f"xp_{gw}"] = round(v, 2)
            row[f"h_{gw}"] = round(h, 3)
            row[f"m_{gw}"] = round(ml_pred[(pid, gw)] * availability(e, k), 3) if (pid, gw) in ml_pred else None
            if (pid, gw) in ml_hauls:
                row["haul"][gw] = round(ml_hauls[(pid, gw)] * availability(e, k), 3)
            tot += v
            fx = team_fx[tid].get(gw, [])
            row["fixtures"][gw] = ", ".join(f"{x['opp']} ({'H' if x['home'] else 'A'})" for x in fx) or "–"
        row["xp_total"] = round(tot, 2)
        row["xp_next"] = row[f"xp_{gws[0]}"]
        row["haul_next"] = row["haul"].get(gws[0])
        row["value_per_m"] = round(tot / row["price"], 2) if row["price"] else 0
        if e.get("status") in ("u", "n"):
            row["hidden"] = True
        rows.append(row)
    df = pd.DataFrame(rows)

    grid = []
    for t in teams:
        grid.append(dict(team=t["id"], name=t["name"], short=t["short_name"], fixtures={
            gw: team_fx[t["id"]].get(gw, []) for gw in gws}))
    meta = dict(next_gw=next_gw, gws=gws, ml=ml_meta, has_defensive_points=has_dc,
                league_goals=dict(home=round(H, 2), away=round(A, 2)))
    return df, grid, meta
