"""Synthetic league used for offline demos/tests (FPL_MOCK=1). Not real data."""
from __future__ import annotations
import datetime as dt
import numpy as np

SYL = "Ka Mo Ri Lu Ten Bra So Vel Dun Ar Is Ny Fe Go Ha Jo".split()
END = "ndo vic son ley ra ko mann tti ez ard ns er".split()

SHORT = "ARS AVL BOU BRE BHA BUR CHE CRY EVE FUL LEE LIV MCI MUN NEW NFO SUN TOT WHU WOL".split()


def round_robin(n):
    t, rounds = list(range(n)), []
    for r in range(n - 1):
        rounds.append([((t[i], t[n - 1 - i]) if (r + i) % 2 == 0 else (t[n - 1 - i], t[i])) for i in range(n // 2)])
        t = [t[0]] + [t[-1]] + t[1:-1]
    return rounds


class MockClient:
    source = "mock"

    def __init__(self, seed=7, played=8):
        rng = self.rng = np.random.default_rng(seed)
        self.played = played
        n = 20
        self.att, self.dfn = rng.lognormal(0, .22, n), rng.lognormal(0, .22, n)
        self.teams = [dict(id=i + 1, name=SHORT[i], short_name=SHORT[i],
                           strength_attack_home=int(1100 + 120 * np.log(self.att[i])),
                           strength_attack_away=int(1080 + 120 * np.log(self.att[i])),
                           strength_defence_home=int(1100 - 120 * np.log(self.dfn[i])),
                           strength_defence_away=int(1080 - 120 * np.log(self.dfn[i]))) for i in range(n)]
        legs = round_robin(n)
        self.fx, fid = [], 1
        for gw, pairs in enumerate(legs + [[(b, a) for a, b in p] for p in legs], start=1):
            for h, a in pairs:
                f = dict(id=fid, event=gw, team_h=h + 1, team_a=a + 1, finished=gw <= played,
                         team_h_score=None, team_a_score=None)
                if gw <= played:
                    f["team_h_score"] = int(rng.poisson(1.5 * self.att[h] * self.dfn[a]))
                    f["team_a_score"] = int(rng.poisson(1.2 * self.att[a] * self.dfn[h]))
                self.fx.append(f); fid += 1
        nxt = dt.datetime.now(dt.timezone.utc).replace(minute=30, second=0, microsecond=0) + dt.timedelta(days=2)
        self.events = [dict(id=g, is_current=(g == played), is_next=(g == played + 1), finished=g <= played,
                            is_previous=(g == played - 1),
                            deadline_time=(nxt + dt.timedelta(days=7 * (g - played - 1))).isoformat().replace("+00:00", "Z"))
                       for g in range(1, 39)]
        self._players(); self._histories()

    def _name(self, pid):
        r = np.random.default_rng(pid * 7919)
        return SYL[r.integers(len(SYL))] + END[r.integers(len(END))] + ("" if pid % 3 else " " + "ABCDEFGHJKLMNPRSTW"[pid % 18] + ".")

    def _players(self):
        rng, self.el, pid = self.rng, [], 1
        layout = {1: (2, [.95, .04]), 2: (7, [.9, .9, .85, .8, .3, .15, .05]),
                  3: (8, [.9, .85, .85, .7, .4, .25, .1, .05]), 4: (4, [.9, .6, .25, .05])}
        for t in range(20):
            for pos, (n, starts) in layout.items():
                for j in range(n):
                    q = float(rng.lognormal(0, .45)) * (1.0 + .25 * (self.att[t] if pos > 2 else self.dfn[t]) - .25)
                    price = round(float(np.clip({1: 4.0, 2: 4.0, 3: 4.5, 4: 4.5}[pos] + q * {1: 1.0, 2: 1.5, 3: 3.0, 4: 3.3}[pos]
                                                * starts[j] ** .5, 4.0, 13.5)) * 2) / 2
                    st, ch = "a", None
                    if rng.random() < .05:
                        st, ch = ("d", 50) if rng.random() < .6 else ("i", 0)
                    self.el.append(dict(id=pid, web_name=self._name(pid), team=t + 1, element_type=pos,
                                        now_cost=int(price * 10), status=st, chance_of_playing_next_round=ch,
                                        news="Knock" if st != "a" else "", selected_by_percent=str(round(float(rng.uniform(0, 30)), 1)),
                                        form="0.0", total_points=0, minutes=0, _q=q, _s=starts[j], _t=t))
                    pid += 1

    def _histories(self):
        rng, self.h = self.rng, {}
        fx_by_gw = {}
        for f in self.fx:
            fx_by_gw.setdefault(f["event"], []).append(f)
        for e in self.el:
            rows, q, pos, t = [], e["_q"], e["element_type"], e["_t"]
            for gw in range(1, self.played + 1):
                f = next(x for x in fx_by_gw[gw] if e["team"] in (x["team_h"], x["team_a"]))
                home = f["team_h"] == e["team"]
                gf, ga = (f["team_h_score"], f["team_a_score"]) if home else (f["team_a_score"], f["team_h_score"])
                mins = 90 if rng.random() < e["_s"] * .92 else (int(rng.integers(10, 40)) if rng.random() < .3 * e["_s"] else 0)
                mf = mins / 90
                rate = {1: 0.0, 2: .06, 3: .14, 4: .33}[pos] * q * self.att[t]
                xg = rate * mf * float(rng.uniform(.7, 1.3))
                xa = {1: .02, 2: .07, 3: .12, 4: .1}[pos] * q * mf * float(rng.uniform(.7, 1.3))
                g, a = int(rng.poisson(xg)), int(rng.poisson(xa))
                saves = int(rng.poisson(2.8 * mf)) if pos == 1 else 0
                cs = 1 if (ga == 0 and mins >= 60) else 0
                bonus = int(rng.choice([0, 1, 2, 3], p=[.8, .08, .07, .05])) if mins >= 60 else 0
                yc = int(rng.random() < .08 * mf)
                dc = int(rng.poisson({1: 0, 2: 8, 3: 7, 4: 4}[pos] * mf)) if mins else 0
                pts = ((2 if mins >= 60 else 1 if mins > 0 else 0) + g * {1: 6, 2: 6, 3: 5, 4: 4}[pos] + a * 3
                       + cs * {1: 4, 2: 4, 3: 1, 4: 0}[pos] - (ga // 2 if pos <= 2 and mins >= 60 else 0)
                       + saves // 3 + bonus - yc + (2 if dc >= {2: 10, 3: 12, 4: 12}.get(pos, 99) else 0))
                rows.append(dict(round=gw, fixture=f["id"], opponent_team=f["team_a"] if home else f["team_h"], was_home=home,
                                 value=e["now_cost"], total_points=int(pts), minutes=mins, goals_scored=g, assists=a,
                                 expected_goals=f"{xg:.2f}", expected_assists=f"{xa:.2f}",
                                 expected_goal_involvements=f"{xg + xa:.2f}", expected_goals_conceded=f"{ga * .8:.2f}",
                                 bonus=bonus, bps=int(pts * 3), saves=saves, yellow_cards=yc, red_cards=0,
                                 defensive_contribution=dc, starts=1 if mins >= 60 else 0, clean_sheets=cs))
            e["total_points"], e["minutes"] = sum(r["total_points"] for r in rows), sum(r["minutes"] for r in rows)
            e["form"] = str(round(np.mean([r["total_points"] for r in rows[-4:]]), 1))
            self.h[e["id"]] = dict(history=rows, history_past=[dict(
                minutes=int(2400 * e["_s"]), goals_scored=int(rng.poisson(rate_ := {1: 0, 2: 2, 3: 5, 4: 9}[pos] * q * e["_s"])),
                assists=int(rng.poisson(3 * e["_s"])), bonus=int(10 * e["_s"]), saves=0, yellow_cards=3, red_cards=0)])

    async def bootstrap(self):
        els = [{k: v for k, v in e.items() if not k.startswith("_")} for e in self.el]
        return dict(elements=els, teams=self.teams, events=self.events)

    async def fixtures(self):
        return self.fx

    async def histories(self, ids, progress=None):
        if progress: progress(len(ids), len(ids))
        return {i: self.h[i] for i in ids if i in self.h}

    def _squad(self, team_id):
        rng = np.random.default_rng(team_id)
        while True:
            chosen, cost, cnt = [], 0.0, {}
            for pos, n in ((1, 2), (2, 5), (3, 5), (4, 3)):
                cands = [e for e in self.el if e["element_type"] == pos and e["_s"] > .3]
                for e in sorted(rng.choice(cands, n, replace=False), key=lambda e: -e["_q"] * e["_s"]):
                    chosen.append(e); cost += e["now_cost"] / 10
                    cnt[e["team"]] = cnt.get(e["team"], 0) + 1
            if cost <= 100 and max(cnt.values()) <= 3:
                return chosen, cost

    def _live(self, gw):
        out = {}
        for pid, h in self.h.items():
            rows = [r for r in h["history"] if r["round"] == gw]
            out[pid] = (sum(r["total_points"] for r in rows), sum(r["minutes"] for r in rows))
        return out

    async def entry(self, team_id):
        return dict(id=team_id, name=f"Demo XI {team_id}", player_first_name="Demo", player_last_name="Manager")

    async def entry_picks(self, team_id, gw):
        sq, cost = self._squad(team_id)
        by = {p: [e for e in sq if e["element_type"] == p] for p in (1, 2, 3, 4)}
        xi = by[1][:1] + by[2][:4] + by[3][:4] + by[4][:2]
        bench = by[1][1:] + by[2][4:] + by[3][4:] + by[4][2:]
        cap = by[4][0]["id"]
        picks = [dict(element=e["id"], position=i + 1, multiplier=(2 if e["id"] == cap else 1) if e in xi else 0,
                      is_captain=e["id"] == cap, is_vice_captain=False) for i, e in enumerate(xi + bench)]
        return dict(picks=picks, entry_history=dict(bank=int(round((100 - cost) * 10)), value=int(cost * 10)), active_chip=None)

    async def entry_history(self, team_id):
        cur, total = [], 0
        rng = np.random.default_rng(team_id + 1)
        for gw in range(1, self.played + 1):
            live, pk = self._live(gw), await self.entry_picks(team_id, gw)
            pts = sum(live.get(p["element"], (0, 0))[0] * p["multiplier"] for p in pk["picks"])
            total += pts
            cur.append(dict(event=gw, points=pts, total_points=total, rank=int(rng.integers(5e5, 8e6)),
                            overall_rank=int(rng.integers(5e5, 8e6)), event_transfers=0, event_transfers_cost=0,
                            points_on_bench=0, bank=pk["entry_history"]["bank"], value=pk["entry_history"]["value"]))
        return dict(current=cur, chips=[])

    async def event_live(self, gw):
        return dict(elements=[dict(id=pid, stats=dict(total_points=p, minutes=m)) for pid, (p, m) in self._live(gw).items()])

    async def entry_transfers(self, team_id):
        return []
