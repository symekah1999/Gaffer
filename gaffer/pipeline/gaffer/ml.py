"""Gradient-boosted correction layer trained on this season's player-fixture history."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .ratings import compute_ratings, team_xg

ROLL_COLS = ["pts", "minutes", "xgi", "xgc", "bonus", "bps", "saves", "dc", "starts"]
FEATS = ["pos", "value", "was_home", "xgf", "xga", "n_prior"] + [
    f"{c}_{s}" for c in ROLL_COLS for s in ("r3", "r5", "all")
]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def history_frame(elements_by_id, histories, teams, fixtures):
    rows = []
    for pid, summ in histories.items():
        el = elements_by_id.get(pid)
        if not el:
            continue
        for r in summ.get("history") or []:
            xg, xa = _num(r.get("expected_goals")), _num(r.get("expected_assists"))
            xgi = _num(r.get("expected_goal_involvements"))
            if np.isnan(xgi):
                xgi = xg + xa
            rows.append(dict(
                player=pid, team=el["team"], pos=el["element_type"], round=r.get("round"),
                fixture=r.get("fixture") or 0, opp=r.get("opponent_team"),
                was_home=1 if r.get("was_home") else 0,
                value=(_num(r.get("value")) / 10) if r.get("value") else el["now_cost"] / 10,
                pts=_num(r.get("total_points")), minutes=_num(r.get("minutes")), xgi=xgi,
                xgc=_num(r.get("expected_goals_conceded")), bonus=_num(r.get("bonus")),
                bps=_num(r.get("bps")), saves=_num(r.get("saves")),
                dc=_num(r.get("defensive_contribution")), starts=_num(r.get("starts")),
            ))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["player", "round", "fixture"]).reset_index(drop=True)
    cache, xgf, xga = {}, [], []
    for t, o, h, rd in zip(df.team, df.opp, df.was_home, df["round"]):
        if rd not in cache:
            cache[rd] = compute_ratings(teams, fixtures, rd)   # only results before that round
        r, H, A = cache[rd]
        a, b = team_xg(r, H, A, t, int(o), bool(h)) if o in r else (np.nan, np.nan)
        xgf.append(a); xga.append(b)
    df["xgf"], df["xga"] = xgf, xga
    return df


def add_rolling(df):
    g = df.groupby("player", sort=False)
    df["n_prior"] = g.cumcount()
    for c in ROLL_COLS:
        sh = g[c].shift(1).groupby(df["player"], sort=False)
        df[f"{c}_r3"] = sh.transform(lambda s: s.rolling(3, min_periods=1).mean())
        df[f"{c}_r5"] = sh.transform(lambda s: s.rolling(5, min_periods=1).mean())
        df[f"{c}_all"] = sh.transform(lambda s: s.expanding(min_periods=1).mean())
    return df


def current_state(df):
    out = {}
    for pid, g in df.groupby("player"):
        d = {"n_prior": len(g)}
        for c in ROLL_COLS:
            s = g[c]
            d[f"{c}_r3"], d[f"{c}_r5"], d[f"{c}_all"] = s.tail(3).mean(), s.tail(5).mean(), s.mean()
        out[pid] = d
    return out


def make_model():
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                             verbose=-1)
    except Exception:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.04, max_leaf_nodes=15,
                                             l2_regularization=5.0)


def run_ml(elements, teams, fixtures, histories, upcoming):
    """upcoming: list of dict(player, gw, pos, value, was_home, xgf, xga). Returns (preds, meta)
    where preds maps (player, gw) -> ML expected points summed over that GW's fixtures."""
    by_id = {e["id"]: e for e in elements}
    df = history_frame(by_id, histories, teams, fixtures)
    meta = {"enabled": False}
    if df.empty:
        return {}, {**meta, "reason": "no history yet"}
    df = add_rolling(df)
    train = df[(df.n_prior >= 2) & df.pts.notna()]
    rounds = sorted(train["round"].unique())
    if len(rounds) < 4 or len(train) < 800:
        return {}, {**meta, "reason": f"only {len(rounds)} gameweeks of data; using the statistical model alone",
                    "rounds": len(rounds)}
    n_val = max(1, min(4, len(rounds) // 4))
    val_rounds = rounds[-n_val:]
    tr, va = train[~train["round"].isin(val_rounds)], train[train["round"].isin(val_rounds)]
    m = make_model().fit(tr[FEATS], tr["pts"])
    pred = m.predict(va[FEATS])
    err = pred - va.pts.values
    base = va["pts_r5"].fillna(va["pts_all"]).fillna(2.0).values
    berr = base - va.pts.values
    rmse, brmse = float(np.sqrt(np.mean(err ** 2))), float(np.sqrt(np.mean(berr ** 2)))
    meta = dict(enabled=True, rounds=len(rounds), validated_on=[int(x) for x in val_rounds],
                n_train=int(len(tr)), n_val=int(len(va)),
                mae=float(np.mean(np.abs(err))), rmse=rmse,
                baseline_mae=float(np.mean(np.abs(berr))), baseline_rmse=brmse,
                skill=float(1 - rmse / brmse),
                corr=float(np.corrcoef(pred, va.pts.values)[0, 1]) if len(va) > 2 else None)
    final = make_model().fit(train[FEATS], train["pts"])
    state = current_state(df)
    up = pd.DataFrame(upcoming)
    if up.empty:
        return {}, meta
    for c in [f for f in FEATS if f not in up.columns]:
        up[c] = [state.get(p, {}).get(c, np.nan) for p in up.player]
    up["n_prior"] = [state.get(p, {}).get("n_prior", 0) for p in up.player]
    up["ml"] = final.predict(up[FEATS])
    out = up.groupby(["player", "gw"])["ml"].sum()
    return {k: float(v) for k, v in out.items()}, meta
