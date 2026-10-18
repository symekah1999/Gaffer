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
DEFAULT_TEAM = (os.getenv("DEFAULT_TEAM_ID") or "").strip()

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
        try:
            row = c.execute("select id from snapshots order by id desc limit 1").fetchone()
        except psycopg.errors.UndefinedTable:
            row = None
        if not row:
            raise HTTPException(503, "No projections yet. The data job is still running or has not been run. In GitHub, open Actions > Update projections and check it finished with a green tick.")
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


def _solver(limit, gap=0.002):
    try:
        s = pulp.HiGHS(msg=False, timeLimit=limit, gapRel=gap)
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
        owned = sum(1 for i in current if i in pool and pool[i]["team"] == tm)   # a club move can leave you with 4
        P += pulp.lpSum(s[i] for i in ids if pool[i]["team"] == tm) <= max(3, owned)
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


def make_card(by_id, i, gws, price=None):
    p = by_id[i]
    xs = [float(p.get(f"xp_{g}") or 0) for g in gws]
    return dict(id=i, name=p["name"], team=p["team_short"], pos=p["pos"], pos_name=p["pos_name"],
                price=p["price"], buy_price=(price or {}).get(i, p["price"]), xp=xs, xp_next=xs[0],
                fixture=(p.get("fixtures") or {}).get(str(gws[0]), "–"), status=p["status"],
                news=p.get("news") or "", p_play=p.get("p_play") or 0,
                haul=(p.get("haul") or {}).get(str(gws[0])))


def best_lineup(ids, xp, pos):
    """Best valid XI and captain from a set of players for one gameweek (exhaustive over formations)."""
    by = {q: sorted([i for i in ids if pos.get(i) == q], key=lambda i: -xp.get(i, 0)) for q in (1, 2, 3, 4)}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3 and by[1] and len(by[2]) >= d and len(by[3]) >= m and len(by[4]) >= f:
                xi = by[1][:1] + by[2][:d] + by[3][:m] + by[4][:f]
                v = sum(xp.get(i, 0) for i in xi)
                if best is None or v > best[0]:
                    best = (v, xi)
    if not best:
        return [], None
    return best[1], max(best[1], key=lambda i: xp.get(i, 0))


def present(res, by_id, gws):
    card = lambda i: make_card(by_id, i, gws, res["price"])
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


POOL_MULTI = dict(POOL)   # a smaller pool scored 4 pts/week less in the 2025-26 simulation
MAX_FT = 5


HIT_MARGIN = 1.0   # a hit must be worth 4 + 1 expected points before the planner takes it


def plan_multi(players, gws, *, current, bank, free_transfers, decay=0.9, hit_cost=4.0, bench_weight=0.08,
               ft_value=1.5, max_per_week=3, exclude=(), force=(), time_limit=20):
    """Week-by-week transfer plan: when to transfer, when to roll a free transfer, when a hit pays off.
    Free transfers bank up to 5; extra transfers cost 4 points; unused transfers left at the end are valued
    at ft_value points each so the plan doesn't waste them in its last week."""
    exclude, force = set(exclude), set(force)
    weight = {p["id"]: sum((decay ** t) * (p.get(f"xp_{g}") or 0) for t, g in enumerate(gws)) for p in players}
    keep = set(current) | force
    for pos, n in POOL_MULTI.items():
        cands = [p for p in players if p["pos"] == pos and p["id"] not in exclude and not p.get("hidden")]
        keep |= {p["id"] for p in sorted(cands, key=lambda p: -weight[p["id"]])[:n]}
    pool = {p["id"]: p for p in players if p["id"] in keep}
    ids, T = list(pool), range(len(gws))
    price = {i: current.get(i, pool[i]["price"]) for i in ids}
    xp = {(i, t): float(pool[i].get(f"xp_{gws[t]}") or 0) for i in ids for t in T}
    budget = bank + sum(current.values())

    P = pulp.LpProblem("plan", pulp.LpMaximize)
    B = lambda n: pulp.LpVariable(n, cat="Binary")
    s = {(i, t): B(f"s{i}_{t}") for i in ids for t in T}
    x = {(i, t): B(f"x{i}_{t}") for i in ids for t in T}
    c = {(i, t): B(f"c{i}_{t}") for i in ids for t in T}
    tin = {(i, t): B(f"in{i}_{t}") for i in ids for t in T}
    tout = {(i, t): B(f"out{i}_{t}") for i in ids for t in T}
    ft = {t: pulp.LpVariable(f"ft{t}", 0, MAX_FT, cat="Integer") for t in range(len(gws) + 1)}
    used = {t: pulp.LpVariable(f"used{t}", 0, MAX_FT, cat="Integer") for t in T}
    paid = {t: pulp.LpVariable(f"paid{t}", 0, max_per_week, cat="Integer") for t in T}
    took_hit = {t: B(f"hit{t}") for t in T}

    P += (pulp.lpSum((decay ** t) * (xp[i, t] * x[i, t] + xp[i, t] * c[i, t] + bench_weight * xp[i, t] * (s[i, t] - x[i, t]))
                     for i in ids for t in T)
          - (hit_cost + HIT_MARGIN) * pulp.lpSum(paid.values()) + ft_value * ft[len(gws)])
    P += ft[0] == min(MAX_FT, max(0, free_transfers))
    teams = {pool[i]["team"] for i in ids}
    for t in T:
        for i in ids:
            prev = (1 if i in current else 0) if t == 0 else s[i, t - 1]
            P += s[i, t] - prev == tin[i, t] - tout[i, t]
            P += tin[i, t] + tout[i, t] <= 1
            P += x[i, t] <= s[i, t]
            P += c[i, t] <= x[i, t]
            if i in exclude: P += s[i, t] == 0
            if i in force: P += s[i, t] == 1
        n = pulp.lpSum(tin[i, t] for i in ids)
        P += n <= max_per_week
        P += used[t] + paid[t] == n
        P += used[t] <= ft[t]
        # FPL uses free transfers first: a hit is only possible once every free transfer is used.
        P += paid[t] <= max_per_week * took_hit[t]
        P += used[t] >= ft[t] - MAX_FT * (1 - took_hit[t])
        P += ft[t + 1] <= ft[t] - used[t] + 1
        P += pulp.lpSum(s[i, t] for i in ids) == 15
        for q, k in ((1, 2), (2, 5), (3, 5), (4, 3)):
            P += pulp.lpSum(s[i, t] for i in ids if pool[i]["pos"] == q) == k
        for tm in teams:
            owned = sum(1 for i in current if i in pool and pool[i]["team"] == tm)
            P += pulp.lpSum(s[i, t] for i in ids if pool[i]["team"] == tm) <= max(3, owned)
        P += pulp.lpSum(price[i] * s[i, t] for i in ids) <= budget + 1e-6
        P += pulp.lpSum(x[i, t] for i in ids) == 11
        P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == 1) == 1
        for q, lo, hi in ((2, 3, 5), (3, 2, 5), (4, 1, 3)):
            P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == q) >= lo
            P += pulp.lpSum(x[i, t] for i in ids if pool[i]["pos"] == q) <= hi
        P += pulp.lpSum(c[i, t] for i in ids) == 1
    P.solve(_solver(time_limit, gap=0.01))
    val = lambda v: (v.value() or 0)
    if sum(val(s[i, 0]) for i in ids) < 14.5:
        raise HTTPException(422, "Couldn't find a valid plan for this squad. Try fewer locked players.")

    weeks, lineups, gw_pts, hits_total = [], [], [], 0
    pos_of = {i: pool[i]["pos"] for i in ids}
    for t in T:
        squad = [i for i in ids if val(s[i, t]) > 0.5]
        xi = [i for i in ids if val(x[i, t]) > 0.5]
        cap = max((i for i in ids if val(c[i, t]) > 0.5), key=lambda i: xp[i, t])
        pts = sum(xp[i, t] for i in xi) + xp[cap, t]
        h = int(round(val(paid[t])))
        hits_total += h
        lineups.append(dict(gw=gws[t], xi=xi, captain=cap)); gw_pts.append(pts)
        weeks.append(dict(gw=gws[t], ft=int(round(val(ft[t]))), hits=h, points=round(pts, 1),
                          ins=[i for i in ids if val(tin[i, t]) > 0.5], outs=[i for i in ids if val(tout[i, t]) > 0.5],
                          captain=cap, squad=squad))
    keep_total = 0.0
    for t in T:
        xpt = {i: xp[i, t] for i in current if i in pool}
        kxi, kcap = best_lineup(list(xpt), xpt, pos_of)
        keep_total += sum(xpt[i] for i in kxi) + (xpt[kcap] if kcap else 0)
    sq0 = weeks[0]["squad"]
    res = dict(squad=sq0, lineups=lineups, gw_points=gw_pts, raw_total=sum(gw_pts), hits=hits_total,
               net_total=sum(gw_pts) - hit_cost * hits_total, cost=sum(price[i] for i in sq0), price=price,
               transfers_out=weeks[0]["outs"], transfers_in=weeks[0]["ins"])
    return res, weeks, keep_total, int(round(val(ft[len(gws)])))


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


CHIPS = [("3xc", "Triple Captain"), ("bboost", "Bench Boost"), ("freehit", "Free Hit"), ("wildcard", "Wildcard")]


def team_state(snap, team_id):
    """Chips used and an estimate of free transfers, from the public FPL history."""
    if snap["source"] == "mock":
        return dict(chips_used=[], free_transfers_estimate=1)
    h = fpl_get(f"/entry/{team_id}/history/")
    chips_used = [dict(name=c["name"], event=c["event"]) for c in h.get("chips", [])]
    wc_fh = {c["event"] for c in chips_used if c["name"] in ("wildcard", "freehit")}
    ft = None
    for row in sorted(h.get("current", []), key=lambda r: r["event"]):
        if ft is None:            # first gameweek: unlimited transfers, 1 free transfer afterwards
            ft = 1; continue
        if row["event"] in wc_fh:
            ft = min(MAX_FT, ft + 1); continue
        paid = (row.get("event_transfers_cost") or 0) // 4
        free_used = max(0, (row.get("event_transfers") or 0) - paid)
        ft = min(MAX_FT, max(0, ft - free_used) + 1)
    return dict(chips_used=chips_used, free_transfers_estimate=ft or 1)


def chip_available(chips_used, chip, gw):
    half = 1 if gw <= 19 else 2
    return not any(c["name"] == chip and (1 if c["event"] <= 19 else 2) == half for c in chips_used)


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
                    next_deadline=s["meta"].get("next_deadline"), auth=bool(SB_URL and SB_KEY),
                    default_team_id=int(DEFAULT_TEAM) if DEFAULT_TEAM.isdigit() else None)
    except HTTPException as e:
        return dict(state="empty" if e.status_code == 503 else "error", message=e.detail)
    except Exception as e:
        return dict(state="error", message=f"Database error: {e.__class__.__name__}. Check DATABASE_URL.")


@app.get("/api/team")
def team_info(team_id: int):
    """Look up a public FPL team so the app can confirm who you connected."""
    s = snapshot()
    if s["source"] == "mock":
        return dict(team_id=team_id, name=f"Demo XI {team_id}", manager="Demo Manager", points=None, rank=None)
    e = fpl_get(f"/entry/{team_id}/")
    return dict(team_id=team_id, name=e.get("name"),
                manager=f"{e.get('player_first_name', '')} {e.get('player_last_name', '')}".strip(),
                points=e.get("summary_overall_points"), rank=e.get("summary_overall_rank"))


MAX_TRACKED = 25


class TrackReq(BaseModel):
    team_id: int


@app.post("/api/track")
def track_team(r: TrackReq):
    """Register a team for weekly results. Capped, and only real FPL teams are accepted."""
    s = snapshot()
    if s["source"] != "mock":
        fpl_get(f"/entry/{r.team_id}/")            # 404s for teams that don't exist
    with db() as c:
        c.execute("create table if not exists tracked_teams (team_id int primary key, added_at timestamptz not null default now())")
        known = c.execute("select 1 from tracked_teams where team_id = %s", (r.team_id,)).fetchone()
        if not known:
            n = c.execute("select count(*) as n from tracked_teams").fetchone()["n"]
            if n >= MAX_TRACKED:
                raise HTTPException(429, "Gaffer is tracking its maximum number of teams right now.")
            c.execute("insert into tracked_teams (team_id) values (%s)", (r.team_id,))
    return dict(tracked=True, new=not known)


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
            try:
                return c.execute("select gw, kind, n, mae, rmse, corr, top10_avg, field_avg, price_top10_avg, form_top10_avg "
                                 "from gw_accuracy order by gw").fetchall()
            except psycopg.errors.UndefinedColumn:
                c.rollback()
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
                haul=p.get("haul_next"),
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
            tracked = rows or c.execute("select 1 from user_settings where team_id = %s", (team_id,)).fetchone() \
                or c.execute("select 1 from tracked_teams where team_id = %s", (team_id,)).fetchone()
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
    plan = None
    if not r.wildcard:
        res, weeks, keep_total, ft_end = plan_multi(s["players"], gws, current=current, bank=bank,
                                                    free_transfers=r.free_transfers, exclude=r.exclude, force=r.force,
                                                    time_limit=15)
        plan = present(res, s["by_id"], gws)
        card = lambda i: make_card(s["by_id"], i, gws, res["price"])
        plan["weeks"] = [dict(gw=w["gw"], ft=w["ft"], hits=w["hits"], points=w["points"],
                              captain=s["by_id"][w["captain"]]["name"],
                              transfers_out=[card(i) for i in w["outs"]], transfers_in=[card(i) for i in w["ins"]])
                         for w in weeks]
        plan["keep_total"] = round(keep_total, 1)
        plan["gain"] = round(plan["net_total"] - keep_total, 1)
        plan["ft_end"] = ft_end
    return dict(plan=plan, plans=plans, recommended=best, bank=bank, picks_gw=s.get("picks_gw"),
                squad_value=round(sum(current.values()), 1))


@app.get("/api/team/state")
def get_team_state(team_id: int):
    return team_state(snapshot(), team_id)


@app.get("/api/chips")
def chips(team_id: int):
    """Best gameweek for each chip you still have, judged on your current squad."""
    s = snapshot(); gws = s["gws"]; by_id = s["by_id"]
    current, bank = load_team(s, team_id)
    used = team_state(s, team_id)["chips_used"]
    counts = {}
    for t in s["fixtures"]:
        for g in gws:
            n = len(t["fixtures"].get(str(g), []))
            c = counts.setdefault(g, dict(doubles=0, blanks=0))
            c["doubles"] += n >= 2; c["blanks"] += n == 0
    rows = []
    for g in gws:
        xp = {i: float(by_id[i].get(f"xp_{g}") or 0) for i in current if i in by_id}
        pos = {i: by_id[i]["pos"] for i in xp}
        xi, cap = best_lineup(list(xp), xp, pos)
        base = sum(xp[i] for i in xi) + (xp[cap] if cap else 0)
        try:
            fh = optimise(s["players"], [g], budget=bank + sum(current.values()), time_limit=4)["gw_points"][0]
        except HTTPException:
            fh = base
        rows.append(dict(gw=g, **counts[g], tc=round(xp.get(cap, 0), 1), tc_player=by_id[cap]["name"] if cap else None,
                         bboost=round(sum(xp[i] for i in xp if i not in xi), 1), freehit=round(max(0.0, fh - base), 1)))
    out = []
    for key, label in CHIPS:
        if key == "wildcard":
            out.append(dict(chip=key, label=label, available=chip_available(used, key, gws[0])))
            continue
        col = {"3xc": "tc"}.get(key, key)
        cands = [r for r in rows if chip_available(used, key, r["gw"])]
        best = max(cands, key=lambda r: r[col]) if cands else None
        out.append(dict(chip=key, label=label, available=chip_available(used, key, gws[0]),
                        best_gw=best["gw"] if best else None, gain=best[col] if best else None,
                        player=best["tc_player"] if (best and key == "3xc") else None))
    return dict(gws=gws, weeks=rows, chips=out, used=used)


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
