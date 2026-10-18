"""Past FPL seasons from the public vaastav/Fantasy-Premier-League archive, reshaped to look exactly like
live FPL API data, so the same model can be trained on them and backtested against them."""
import io, os, time
from pathlib import Path
import httpx
import pandas as pd

BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
CACHE = Path(os.getenv("HISTORY_CACHE") or Path(__file__).resolve().parent.parent.parent / ".cache" / "history")
POS = {"GK": 1, "GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
TRAIN_SEASONS = ["2022-23", "2023-24", "2024-25"]   # expected-goals data exists from 2022-23 onward


def _csv(season, name):
    f = CACHE / season / name.replace("/", "_")
    if not f.exists() or time.time() - f.stat().st_mtime > 30 * 86400:
        f.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(f"{BASE}/{season}/{name}", timeout=60, follow_redirects=True)
        r.raise_for_status()
        f.write_bytes(r.content)
    return pd.read_csv(f, low_memory=False)


def load_season(season, prev_season=None):
    """Returns (bootstrap, fixtures, histories) shaped like the live FPL API, plus actual points {gw: {pid: (pts, mins)}}."""
    gw = _csv(season, "gws/merged_gw.csv")
    gw = gw[gw["position"].isin(POS)]                       # drop assistant-manager rows
    teams_df = _csv(season, "teams.csv")
    fx = _csv(season, "fixtures.csv")
    pr = _csv(season, "players_raw.csv")
    teams = [dict(id=int(t.id), name=t["name"], short_name=t.short_name,
                  **{k: int(t[k]) for k in ("strength_attack_home", "strength_attack_away",
                                            "strength_defence_home", "strength_defence_away")})
             for _, t in teams_df.iterrows()]
    fixtures = [dict(id=int(f.id), event=int(f.event) if pd.notna(f.event) else None, team_h=int(f.team_h),
                     team_a=int(f.team_a), finished=True,
                     team_h_score=int(f.team_h_score) if pd.notna(f.team_h_score) else None,
                     team_a_score=int(f.team_a_score) if pd.notna(f.team_a_score) else None)
                for _, f in fx.iterrows()]
    past = {}
    if prev_season:
        pp = _csv(prev_season, "players_raw.csv")
        for _, r in pp.iterrows():
            past[int(r.code)] = {k: (None if pd.isna(r.get(k)) else r.get(k)) for k in
                                 ("minutes", "goals_scored", "assists", "expected_goals", "expected_assists",
                                  "bonus", "saves", "yellow_cards", "red_cards")}
    pos_of = gw.groupby("element")["position"].first().map(POS).to_dict()
    code_of = dict(zip(pr.id.astype(int), pr.code.astype(int)))
    elements = []
    for _, p in pr.iterrows():
        pid = int(p.id)
        if pid not in pos_of:
            continue
        elements.append(dict(id=pid, web_name=p.web_name, team=int(p.team), element_type=int(pos_of[pid]),
                             now_cost=int(p.now_cost), status="a", chance_of_playing_next_round=None, news="",
                             selected_by_percent=str(p.get("selected_by_percent", 0)), form="0",
                             total_points=int(p.get("total_points", 0)), minutes=int(p.get("minutes", 0))))
    cols = ["round", "fixture", "opponent_team", "was_home", "value", "total_points", "minutes", "goals_scored",
            "assists", "expected_goals", "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
            "bonus", "bps", "saves", "yellow_cards", "red_cards", "starts", "kickoff_time", "xP"]
    cols = [c for c in cols if c in gw.columns]
    team_id = {t["name"]: t["id"] for t in teams}
    gw["team_id"] = gw["team"].map(team_id)
    cols.append("team_id")
    hist = {}
    for pid, g in gw.sort_values(["round", "kickoff_time"]).groupby("element"):
        rows = g[cols].to_dict("records")
        for r in rows:
            r["was_home"] = bool(r["was_home"]) if not isinstance(r["was_home"], str) else r["was_home"] == "True"
        prior = past.get(code_of.get(int(pid)))
        hist[int(pid)] = {"history": rows, "history_past": [prior] if prior else []}
    actual = {}
    for (rd, pid), g in gw.groupby(["round", "element"]):
        actual.setdefault(int(rd), {})[int(pid)] = (int(g.total_points.sum()), int(g.minutes.sum()))
    official = {}
    for (rd, pid), g in gw.groupby(["round", "element"]):
        official.setdefault(int(rd), {})[int(pid)] = float(g.xP.astype(float).max()) if "xP" in g else None
    events = [dict(id=i, is_next=False, is_current=False, finished=True) for i in range(1, 39)]
    boot = dict(elements=elements, teams=teams, events=events)
    return boot, fixtures, hist, actual, official


def training_frame(seasons=TRAIN_SEASONS, before=None):
    """Rolling-feature rows for the ML layer from full past seasons (stopping before season `before`)."""
    from . import ml
    frames = []
    for i, s in enumerate(seasons):
        if before and s >= before:
            break
        boot, fixtures, hist, _, _ = load_season(s, seasons[i - 1] if i else None)
        by_id = {e["id"]: e for e in boot["elements"]}
        df = ml.history_frame(by_id, hist, boot["teams"], fixtures)
        if df.empty:
            continue
        df = ml.add_rolling(df)
        df["season"] = s
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def default_seasons(start_year, n=4):
    """The n seasons before the one starting in start_year, e.g. 2026 -> 2022-23 .. 2025-26."""
    return [f"{y}-{str(y + 1)[2:]}" for y in range(start_year - n, start_year)]


def load_history(seasons, log=print):
    """Training rows from past seasons; seasons missing from the archive are skipped."""
    from . import ml
    frames, prev = [], None
    for s in seasons:
        try:
            boot, fixtures, hist, _, _ = load_season(s, prev)
            df = ml.history_frame({e["id"]: e for e in boot["elements"]}, hist, boot["teams"], fixtures)
            if not df.empty:
                df = ml.add_rolling(df)
                df["season"] = s
                frames.append(df)
                log(f"  {s}: {len(df):,} player-matches")
        except Exception as e:
            log(f"  {s}: skipped ({e.__class__.__name__})")
        prev = s
    return pd.concat(frames, ignore_index=True) if frames else None
