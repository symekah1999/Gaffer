"""Gradient-boosted models trained on past seasons and this one: expected points and haul chance."""
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


HAUL = 10   # points for a "haul"


def make_model():
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=60,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    except Exception:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_leaf_nodes=31, l2_regularization=5.0)


def make_classifier():
    try:
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=80,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.04, max_leaf_nodes=31, l2_regularization=5.0)


def _auc(y, p):
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None
    except Exception:
        return None


def _score(model, clf, test):
    pred = model.predict(test[FEATS]); y = test.pts.values
    base = test["pts_r5"].fillna(test["pts_all"]).fillna(2.0).values
    rmse, brmse = float(np.sqrt(np.mean((pred - y) ** 2))), float(np.sqrt(np.mean((base - y) ** 2)))
    out = dict(n=int(len(test)), mae=float(np.mean(np.abs(pred - y))), rmse=rmse,
               baseline_mae=float(np.mean(np.abs(base - y))), baseline_rmse=brmse, skill=float(1 - rmse / brmse),
               corr=float(np.corrcoef(pred, y)[0, 1]) if len(test) > 2 else None)
    if clf is not None:
        out["haul_auc"] = _auc((y >= HAUL).astype(int), clf.predict_proba(test[FEATS])[:, 1])
        out["haul_rate"] = float((y >= HAUL).mean())
    return out


def run_ml(elements, teams, fixtures, histories, upcoming, extra=None, evaluate=True):
    """upcoming: list of dict(player, gw, pos, value, was_home, xgf, xga); extra: rows from past seasons.
    Returns (points, hauls, meta): expected ML points and the chance of a 10+ haul per (player, gw)."""
    by_id = {e["id"]: e for e in elements}
    df = history_frame(by_id, histories, teams, fixtures)
    df = add_rolling(df) if not df.empty else df
    cur = df[(df.n_prior >= 2) & df.pts.notna()] if not df.empty else df
    ext = extra[extra.pts.notna() & (extra.n_prior >= 2)] if extra is not None and len(extra) else None
    rounds = sorted(cur["round"].unique()) if len(cur) else []
    if ext is None and (len(rounds) < 4 or len(cur) < 800):
        return {}, {}, {"enabled": False, "rounds": len(rounds),
                        "reason": f"only {len(rounds)} gameweeks of data; using the statistical model alone"}
    meta = dict(enabled=True, rounds=len(rounds), history_rows=int(0 if ext is None else len(ext)),
                history_seasons=sorted(ext["season"].unique().tolist()) if ext is not None else [])

    # Full-season test: train on earlier seasons only, predict every match of the latest one.
    if evaluate and ext is not None and ext["season"].nunique() >= 2:
        last = ext["season"].max()
        tr, te = ext[ext.season != last], ext[ext.season == last]
        meta["season_test"] = dict(season=last, **_score(make_model().fit(tr[FEATS], tr.pts),
                                                         make_classifier().fit(tr[FEATS], (tr.pts >= HAUL).astype(int)), te))
    # This season's check: the last few gameweeks, unseen in training.
    if len(rounds) >= 4:
        val = rounds[-max(1, min(4, len(rounds) // 4)):]
        va = cur[cur["round"].isin(val)]
        tr = pd.concat([x for x in (ext, cur[~cur["round"].isin(val)]) if x is not None and len(x)])
        sc = _score(make_model().fit(tr[FEATS], tr.pts), None, va)
        meta.update(validated_on=[int(v) for v in val], n_val=sc.pop("n"), **sc)
    elif "season_test" in meta:
        st = meta["season_test"]
        meta.update(validated_on=[], n_val=st["n"], mae=st["mae"], rmse=st["rmse"], baseline_mae=st["baseline_mae"],
                    baseline_rmse=st["baseline_rmse"], skill=st["skill"], corr=st["corr"])
    else:
        meta.update(validated_on=[], skill=0.0)

    pool = pd.concat([x for x in (ext, cur) if x is not None and len(x)])
    reg = make_model().fit(pool[FEATS], pool.pts)
    clf = make_classifier().fit(pool[FEATS], (pool.pts >= HAUL).astype(int))
    up = pd.DataFrame(upcoming)
    if up.empty:
        return {}, {}, meta
    state = current_state(df) if not df.empty else {}
    for c in [f for f in FEATS if f not in up.columns]:
        up[c] = [state.get(p, {}).get(c, np.nan) for p in up.player]
    up["n_prior"] = [state.get(p, {}).get("n_prior", 0) for p in up.player]
    up["ml"] = reg.predict(up[FEATS])
    up["miss"] = 1 - clf.predict_proba(up[FEATS])[:, 1]          # chance of no haul in that fixture
    g = up.groupby(["player", "gw"])
    pts = {k: float(v) for k, v in g["ml"].sum().items()}
    hauls = {k: float(1 - v) for k, v in g["miss"].prod().items()}  # double gameweeks: two chances
    return pts, hauls, meta
