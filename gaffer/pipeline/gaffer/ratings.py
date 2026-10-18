"""Team strength ratings derived from real results, shrunk towards FPL's own strength numbers."""
from __future__ import annotations
import numpy as np


def _norm(teams, key):
    vals = np.array([(t.get(key) or 1100) for t in teams], float)
    m = vals.mean()
    return {t["id"]: (t.get(key) or 1100) / m for t in teams}


def compute_ratings(teams, fixtures, upto_gw, k=5.0):
    """Attack / defence multipliers per team, home and away, using fixtures with event < upto_gw.

    Returns (ratings, H, A) where H / A are league-average home / away goals.
    k is the number of pseudo-games of prior (FPL strength) mixed into the observed record.
    """
    played = [
        f for f in fixtures
        if f.get("event") is not None and f["event"] < upto_gw
        and f.get("team_h_score") is not None and f.get("team_a_score") is not None
    ]
    if played:
        H = max(float(np.mean([f["team_h_score"] for f in played])), 0.8)
        A = max(float(np.mean([f["team_a_score"] for f in played])), 0.6)
    else:
        H, A = 1.5, 1.2
    sah, saa = _norm(teams, "strength_attack_home"), _norm(teams, "strength_attack_away")
    sdh, sda = _norm(teams, "strength_defence_home"), _norm(teams, "strength_defence_away")
    st = {t["id"]: dict(nh=0, na=0, gf_h=0.0, ga_h=0.0, gf_a=0.0, ga_a=0.0) for t in teams}
    for f in played:
        h, a = f["team_h"], f["team_a"]
        if h not in st or a not in st:
            continue
        st[h]["nh"] += 1; st[h]["gf_h"] += f["team_h_score"]; st[h]["ga_h"] += f["team_a_score"]
        st[a]["na"] += 1; st[a]["gf_a"] += f["team_a_score"]; st[a]["ga_a"] += f["team_h_score"]
    r = {}
    for t in teams:
        i, s = t["id"], st[t["id"]]
        r[i] = dict(
            att_h=(s["gf_h"] / H + k * sah[i]) / (s["nh"] + k),
            att_a=(s["gf_a"] / A + k * saa[i]) / (s["na"] + k),
            def_h=(s["ga_h"] / A + k / sdh[i]) / (s["nh"] + k),   # goals conceded multiplier
            def_a=(s["ga_a"] / H + k / sda[i]) / (s["na"] + k),
        )
    return r, H, A


def team_xg(r, H, A, team, opp, home):
    """Expected goals (for, against) for `team` in a fixture against `opp`."""
    if home:
        return H * r[team]["att_h"] * r[opp]["def_a"], A * r[opp]["att_a"] * r[team]["def_h"]
    return A * r[team]["att_a"] * r[opp]["def_h"], H * r[opp]["att_h"] * r[team]["def_a"]


def baselines(r, H, A, team):
    """Team's typical attacking output / goals conceded / dominance, used to normalise fixture effects."""
    L = (H + A) / 2
    att = (r[team]["att_h"] + r[team]["att_a"]) / 2
    dfn = (r[team]["def_h"] + r[team]["def_a"]) / 2
    return L * att, L * dfn, float(np.sqrt(att / dfn))
