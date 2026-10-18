"""Gaffer API (Vercel Python function). Reads projections from Neon, optimises squads,
saves user settings for Supabase-authenticated users."""
import os, random, time
from typing import List, Optional

import httpx, psycopg, pulp
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field

DB_URL = os.getenv("DATABASE_URL")
SB_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_ANON_KEY")
FPL = "https://fantasy.premierleague.com/api"
UA = {"User-Agent": "Mozilla/5.0 (gaffer fpl planner)"}
HORIZON = 8

app = FastAPI(title="Gaffer API")


@app.middleware("http")
async def accept_api_prefix(request, call_next):
    """Routes are declared as /api/...; accept the path with or without the prefix, so the app works
    whether the platform forwards the original path or strips the /api mount prefix."""
    path = request.scope["path"]
    if not path.startswith("/api"):
        request.scope["path"] = "/api" + path
    return await call_next(request)


# ---------------------------------------------------------------- data
def db():
    if not DB_URL:
        raise HTTPException(500, "DATABASE_URL is not set on the server.")
    return psycopg.connect(DB_URL, row_factory=dict_row, connect_timeout=10)


_snap = {"id": None, "checked": 0.0, "data": None}


def snapshot():
    """Latest snapshot, cached in the warm function for 2 minutes."""
    if _snap["data"] and time.time() - _snap["checked"] < 120:
        return _snap["data"]
    with db() as c:
        row = c.execute("select id from snapshots order by id desc limit 1").fetchone()
        if not row:
            raise HTTPException(503, "No projections yet. In GitHub, open Actions > Update projections > Run workflow.")
        if row["id"] != _snap["id"]:
            s = c.execute("select * from snapshots where id = %s", (row["id"],)).fetchone()
            s["by_id"] = {p["id"]: p for p in s["players"]}
            _snap.update(id=row["id"], data=s)
    _snap["checked"] = time.time()
    return _snap["data"]


# ---------------------------------------------------------------- auth
_tokens: dict = {}


def user_id(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to save your settings.")
    hit = _tokens.get(authorization)
    if hit and hit[1] > time.time():
        return hit[0]
    if not (SB_URL and SB_KEY):
        raise HTTPException(500, "Supabase is not configured on the server.")
    r = httpx.get(f"{SB_URL}/auth/v1/user", headers={"Authorization": authorization, "apikey": SB_KEY}, timeout=10)
    if r.status_code != 200:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    uid = r.json()["id"]
    _tokens[authorization] = (uid, time.time() + 300)
    return uid


# ---------------------------------------------------------------- optimiser
POOL = {1: 22, 2: 70, 3: 80, 4: 40}


def _solver(limit):
    try:
        s = pulp.HiGHS(msg=False, timeLimit=limit)
        if s.available():
            return s
    except Exception:
        pass
    return pulp.PULP_CBC_CMD(msg=False, timeLimit=limit, gapRel=0.0005)


def optimise(players, gws, *, decay=0.92, budget=100.0, current=None, bank=0.0, free_transfers=1,
             max_transfers=None, unlimited=False, hit_cost=4.0, bench_weight=0.08,
             exclude=(), force=(), time_limit=10):
    current, exclude, force = current or {}, set(exclude), set(force)
    weight = {p["id"]: sum((decay ** t) * (p.get(f"xp_{g}") or 0) for t, g in enumerate(gws)) for p in players}
    keep = set(current) | force
    for pos, n in POOL.items():
        cands = [p for p in players if p["pos"] == pos and p["id"] not in exclude and not p.get("hidden")]
        keep |= {p["id"] for p in sorted(cands, key=lambda p: -weight[p["id"]])[:n]}
    pool = {p["id"]: p for p in players if p["id"] in keep}
    ids, T = list(pool), range(len(gws))
    price = {i: current.get(i, pool[i]["price"]) for i in ids}
    xp = {(i, t): float(pool[i].get(f"xp_{gws[t]}") or 0) for i in ids for t in T}
    wt = [decay ** t for t in T]

    P = pulp.LpProblem("fpl", pulp.LpMaximize)
    s = {i: pulp.LpVariable(f"s{i}", cat="Binary") for i in ids}
    x = {(i, t): pulp.LpVariable(f"x{i}_{t}", cat="Binary") for i in ids for t in T}
    c = {(i, t): pulp.LpVariable(f"c{i}_{t}", cat="Binary") for i in ids for t in T}
    hit = pulp.LpVariable("hits", lowBound=0)
    obj = pulp.lpSum(wt[t] * (xp[i, t] * x[i, t] + xp[i, t] * c[i, t] + bench_weight * xp[i, t] * (s[i] - x[i, t]))
                     for i in ids for t in T)
    out = pulp.lpSum(1 - s[i] for i in ids if i in current) if current else 0
    if current and not unlimited:
        obj = obj - hit_cost * hit
        P += hit >= out - free_transfers
        if max_transfers is not None:
            P += out <= max_transfers
    P += obj
    P += pulp.lpSum(s.values()) == 15
    for p, n in ((1, 2), (2, 5), (3, 5), (4, 3)):
        P += pulp.lpSum(s[i] for i in ids if pool[i]["pos"] == p) == n
    for tm in {pool[i]["team"] for i in ids}:
        P += pulp.lpSum(s[i] for i in ids if pool[i]["team"] == tm) <= 3
    P += pulp.lpSum(price[i] * s[i] for i in ids) <= ((bank + sum(current.values())) if current else budget) + 1e-6
    for i in ids:
        if i in exclude: P += s[i] == 0
        if i in force: P += s[i] == 1
    for t in T:
        P += pulp.lpSum(x[i, t] for i in ids) == 11
        P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == 1) == 1
        for p, lo, hi in ((2, 3, 5), (3, 2, 5), (4, 1, 3)):
            P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == p) >= lo
            P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == p) <= hi
        P += pulp.lpSum(c[i, t] for i in ids) == 1
        for i in ids:
            P += x[i, t] <= s[i]
            P += c[i, t] <= x[i, t]
    P.solve(_solver(time_limit))
    squad = [i for i in ids if (s[i].value() or 0) > 0.5]
    if len(squad) != 15:
        raise HTTPException(422, "No valid squad fits those constraints. Try a bigger budget or fewer locked players.")
    lineups, gw_pts = [], []
    for t in T:
        xi = [i for i in ids if (x[i, t].value() or 0) > 0.5]
        cap = max((i for i in ids if (c[i, t].value() or 0) > 0.5), key=lambda i: xp[i, t])
        lineups.append(dict(gw=gws[t], xi=xi, captain=cap))
        gw_pts.append(sum(xp[i, t] for i in xi) + xp[cap, t])
    outs = [i for i in current if i not in squad]
    hits = 0 if (unlimited or not current) else max(0, len(outs) - free_transfers)
    return dict(squad=squad, lineups=lineups, gw_points=gw_pts, raw_total=sum(gw_pts),
                transfers_out=outs, transfers_in=[i for i in squad if i not in current] if current else [],
                hits=hits, net_total=sum(gw_pts) - hit_cost * hits, cost=sum(price[i] for i in squad), price=price)


def present(res, by_id, gws):
    def card(i):
        p = by_id[i]
        xs = [float(p.get(f"xp_{g}") or 0) for g in gws]
        return dict(id=i, name=p["name"], team=p["team_short"], pos=p["pos"], pos_name=p["pos_name"],
                    price=p["price"], buy_price=res["price"].get(i, p["price"]), xp=xs, xp_next=xs[0],
                    fixture=(p.get("fixtures") or {}).get(str(gws[0]), "–"), status=p["status"],
                    news=p.get("news") or "", p_play=p.get("p_play") or 0)
    first = res["lineups"][0]
    xi = sorted((card(i) for i in first["xi"]), key=lambda p: (p["pos"], -p["xp_next"]))
    rest = [i for i in res["squad"] if i not in first["xi"]]
    bench = [card(i) for i in rest if by_id[i]["pos"] == 1] + \
        sorted((card(i) for i in rest if by_id[i]["pos"] != 1), key=lambda p: -p["xp_next"])
    vice = max((p for p in xi if p["id"] != first["captain"]), key=lambda p: p["xp_next"])["id"]
    return dict(gw=first["gw"], gws=gws, xi=xi, bench=bench, captain=first["captain"], vice=vice,
                gw_points=[round(v, 1) for v in res["gw_points"]], raw_total=round(res["raw_total"], 1),
                hits=res["hits"], net_total=round(res["net_total"], 1), cost=round(res["cost"], 1),
                transfers_out=[card(i) for i in res["transfers_out"]],
                transfers_in=[card(i) for i in res["transfers_in"]])


# ---------------------------------------------------------------- FPL team
def fpl_get(path):
    try:
        r = httpx.get(FPL + path, headers=UA, timeout=15, follow_redirects=True)
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach the FPL site. Try again in a minute.")
    if r.status_code == 404:
        raise HTTPException(404, "Team not found. Use the number in the URL of your FPL Points page.")
    if r.status_code != 200:
        raise HTTPException(502, f"The FPL site returned an error ({r.status_code}). Try again in a minute.")
    return r.json()


def mock_team(snap, team_id):
    rng = random.Random(team_id)
    pl = [p for p in snap["players"] if not p.get("hidden") and (p.get("e_min") or 0) > 30]
    while True:
        squad, cnt = [], {}
        for pos, n in ((1, 2), (2, 5), (3, 5), (4, 3)):
            squad += rng.sample([p for p in pl if p["pos"] == pos], n)
        for p in squad:
            cnt[p["team"]] = cnt.get(p["team"], 0) + 1
        cost = sum(p["price"] for p in squad)
        if cost <= 100 and max(cnt.values()) <= 3:
            return {p["id"]: p["price"] for p in squad}, round(100 - cost, 1)


def load_team(snap, team_id):
    if snap["source"] == "mock":
        return mock_team(snap, team_id)
    gw = snap.get("picks_gw")
    if not gw:
        raise HTTPException(400, "No gameweek has been played yet, so there is no squad to load.")
    picks = fpl_get(f"/entry/{team_id}/event/{gw}/picks/")
    transfers = fpl_get(f"/entry/{team_id}/transfers/")
    bought = {}
    for t in sorted(transfers, key=lambda t: t.get("time", "")):
        bought[t["element_in"]] = t["element_in_cost"] / 10
    current = {}
    for pk in picks["picks"]:
        p = snap["by_id"].get(pk["element"])
        if not p:
            continue
        now, buy = p["price"], bought.get(pk["element"]) or p.get("start_price") or p["price"]
        current[p["id"]] = round(buy + int(round((now - buy) * 10)) // 2 / 10, 1) if now > buy else now
    return current, picks["entry_history"]["bank"] / 10


# ---------------------------------------------------------------- routes
class SquadReq(BaseModel):
    budget: float = Field(100.0, ge=80, le=120)
    horizon: int = Field(5, ge=1, le=HORIZON)
    decay: float = Field(0.92, ge=0.5, le=1.0)
    exclude: List[int] = []
    force: List[int] = []


class TransferReq(BaseModel):
    team_id: int
    free_transfers: int = Field(1, ge=0, le=5)
    horizon: int = Field(5, ge=1, le=HORIZON)
    decay: float = Field(0.92, ge=0.5, le=1.0)
    max_transfers: int = Field(3, ge=0, le=4)
    wildcard: bool = False
    exclude: List[int] = []
    force: List[int] = []


class Settings(BaseModel):
    team_id: Optional[int] = None
    free_transfers: int = Field(1, ge=0, le=5)
    horizon: int = Field(5, ge=1, le=HORIZON)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    try:
        s = snapshot()
        return dict(state="ready", next_gw=s["next_gw"], source=s["source"], updated_at=s["created_at"].isoformat(),
                    next_deadline=s["meta"].get("next_deadline"), auth=bool(SB_URL and SB_KEY))
    except HTTPException as e:
        return dict(state="empty" if e.status_code == 503 else "error", message=e.detail)
    except Exception as e:
        return dict(state="error", message=f"Database error: {e.__class__.__name__}. Check DATABASE_URL.")


@app.get("/api/players")
def players():
    s = snapshot()
    return dict(gws=s["gws"], players=[p for p in s["players"] if not p.get("hidden")])


@app.get("/api/fixtures")
def fixtures():
    s = snapshot()
    return dict(gws=s["gws"], teams=s["fixtures"])


def accuracy_rows():
    try:
        with db() as c:
            return c.execute("select gw, kind, n, mae, rmse, corr, top10_avg, field_avg from gw_accuracy order by gw").fetchall()
    except psycopg.errors.UndefinedTable:
        return []


@app.get("/api/model")
def model_info():
    s = snapshot()
    return dict(source=s["source"], updated_at=s["created_at"].isoformat(), history=accuracy_rows(), **s["meta"])


def _card(p, gws):
    return dict(id=p["id"], name=p["name"], team=p["team_short"], pos=p["pos"], pos_name=p["pos_name"],
                price=p["price"], selected=p.get("selected") or 0, form=p.get("form") or 0,
                xp_next=p.get("xp_next") or 0, xp3=round(sum(p.get(f"xp_{g}") or 0 for g in gws[:3]), 1),
                xp5=round(sum(p.get(f"xp_{g}") or 0 for g in gws[:5]), 1),
                xp_total=p.get("xp_total") or 0, p_play=p.get("p_play") or 0, news=p.get("news") or "",
                fixture=(p.get("fixtures") or {}).get(str(gws[0]), "–"))


@app.get("/api/insights")
def insights():
    s = snapshot(); gws = s["gws"]
    P = [p for p in s["players"] if not p.get("hidden")]
    fit = [p for p in P if (p.get("p_play") or 0) >= 0.75]
    card = lambda p: _card(p, gws)
    top = lambda rows, key, n: [card(p) for p in sorted(rows, key=key)[:n]]
    xp3 = lambda p: sum(p.get(f"xp_{g}") or 0 for g in gws[:3])
    xp5 = lambda p: sum(p.get(f"xp_{g}") or 0 for g in gws[:5])
    value = {name: top([p for p in fit if p["pos"] == pos], lambda p: -xp5(p) / p["price"], 4)
             for pos, name in ((1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD"))}
    hot = [p for p in fit if (p.get("form") or 0) - (p.get("xp_next") or 0) >= 2.0 and (p.get("selected") or 0) >= 3]
    cold = [p for p in fit if (p.get("xp_next") or 0) - (p.get("form") or 0) >= 1.5 and (p.get("minutes") or 0) >= 180]
    runs = []
    for t in s["fixtures"]:
        fx = [f for g in gws[:4] for f in t["fixtures"].get(str(g), [])]
        runs.append(dict(team=t["short"], name=t["name"], att=round(sum(f["xgf"] for f in fx), 2),
                         dfn=round(sum(f["xga"] for f in fx), 2),
                         games=[", ".join(f"{f['opp']} ({'H' if f['home'] else 'A'})" for f in t["fixtures"].get(str(g), [])) or "–"
                                for g in gws[:4]]))
    return dict(
        gws=gws,
        captains=top(fit, lambda p: -(p.get("xp_next") or 0), 5),
        differentials=top([p for p in fit if (p.get("selected") or 0) < 8], lambda p: -xp3(p), 6),
        value=value,
        hot=top(hot, lambda p: -((p.get("form") or 0) - (p.get("xp_next") or 0)), 5),
        cold=top(cold, lambda p: -((p.get("xp_next") or 0) - (p.get("form") or 0)), 5),
        template=top(P, lambda p: -(p.get("selected") or 0), 8),
        injuries=top([p for p in P if (1 if p.get("p_play") is None else p["p_play"]) < 1 and (p.get("selected") or 0) >= 2],
                     lambda p: -(p.get("selected") or 0), 8),
        attack_runs=sorted(runs, key=lambda r: -r["att"])[:5],
        defence_runs=sorted(runs, key=lambda r: r["dfn"])[:5],
        track=accuracy_rows(),
    )


@app.get("/api/reports")
def team_reports(team_id: int):
    try:
        with db() as c:
            rows = c.execute("select data from team_reports where team_id = %s order by gw", (team_id,)).fetchall()
            tracked = rows or c.execute("select 1 from user_settings where team_id = %s", (team_id,)).fetchone()
    except psycopg.errors.UndefinedTable:
        rows, tracked = [], False
    weeks = [r["data"] for r in rows]
    return dict(team_id=team_id, tracked=bool(tracked), weeks=weeks,
                team_name=weeks[-1]["team_name"] if weeks else None, manager=weeks[-1]["manager"] if weeks else None)


@app.post("/api/optimize/squad")
def optimize_squad(r: SquadReq):
    s = snapshot(); gws = s["gws"][: r.horizon]
    res = optimise(s["players"], gws, decay=r.decay, budget=r.budget, exclude=r.exclude, force=r.force, time_limit=20)
    return present(res, s["by_id"], gws)


@app.post("/api/optimize/transfers")
def optimize_transfers(r: TransferReq):
    s = snapshot(); gws = s["gws"][: r.horizon]
    current, bank = load_team(s, r.team_id)
    plans, seen = [], set()
    ks = [None] if r.wildcard else range(0, r.max_transfers + 1)
    for k in ks:
        res = optimise(s["players"], gws, decay=r.decay, current=current, bank=bank, unlimited=r.wildcard,
                       free_transfers=r.free_transfers, max_transfers=k, exclude=r.exclude, force=r.force,
                       time_limit=20 if r.wildcard else 8)
        key = tuple(sorted(res["transfers_in"]))
        if key in seen:
            continue
        seen.add(key)
        plans.append(dict(k=len(res["transfers_in"]), **present(res, s["by_id"], gws)))
    base = next((p for p in plans if p["k"] == 0), plans[0])
    for p in plans:
        p["gain"] = round(p["net_total"] - base["net_total"], 1)
    best = max(range(len(plans)), key=lambda i: plans[i]["net_total"])
    return dict(plans=plans, recommended=best, bank=bank, picks_gw=s.get("picks_gw"),
                squad_value=round(sum(current.values()), 1))


@app.get("/api/me")
def get_me(uid: str = Depends(user_id)):
    with db() as c:
        row = c.execute("select team_id, free_transfers, horizon from user_settings where user_id = %s", (uid,)).fetchone()
    return row or dict(team_id=None, free_transfers=1, horizon=5)


@app.put("/api/me")
def put_me(body: Settings, uid: str = Depends(user_id)):
    with db() as c:
        c.execute("""insert into user_settings (user_id, team_id, free_transfers, horizon, updated_at)
                     values (%s, %s, %s, %s, now())
                     on conflict (user_id) do update set team_id = excluded.team_id,
                       free_transfers = excluded.free_transfers, horizon = excluded.horizon, updated_at = now()""",
                  (uid, body.team_id, body.free_transfers, body.horizon))
    return body
