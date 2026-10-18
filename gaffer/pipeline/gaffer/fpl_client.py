"""Async client for the public FPL API with on-disk caching and polite concurrency."""
from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path
import httpx

BASE = "https://fantasy.premierleague.com/api"
CACHE = Path(os.getenv("CACHE_DIR") or Path(__file__).resolve().parent.parent / ".cache")
CACHE.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (fpl-planner personal project)"}


class FPLClient:
    source = "live"

    def __init__(self, concurrency: int = 8):
        self.sem = asyncio.Semaphore(concurrency)

    async def _get(self, client: httpx.AsyncClient, path: str, ttl: int):
        f = CACHE / (path.strip("/").replace("/", "_") + ".json")
        if f.exists() and time.time() - f.stat().st_mtime < ttl:
            return json.loads(f.read_text())
        last = None
        for attempt in range(4):
            try:
                async with self.sem:
                    r = await client.get(BASE + path, timeout=30)
                if r.status_code == 429:
                    await asyncio.sleep(2 ** attempt); continue
                if r.status_code == 404:
                    raise FileNotFoundError(path)
                r.raise_for_status()
                data = r.json()
                f.write_text(json.dumps(data))
                return data
            except FileNotFoundError:
                raise
            except httpx.HTTPError as e:
                last = e
                await asyncio.sleep(1 + attempt)
        if f.exists():                      # stale cache beats failing
            return json.loads(f.read_text())
        raise RuntimeError(f"FPL API unavailable for {path}: {last}")

    def _client(self):
        return httpx.AsyncClient(headers=HEADERS, follow_redirects=True)

    async def bootstrap(self):
        async with self._client() as c:
            return await self._get(c, "/bootstrap-static/", 300)

    async def fixtures(self):
        async with self._client() as c:
            return await self._get(c, "/fixtures/", 600)

    async def histories(self, ids, progress=None):
        out, done = {}, 0
        async with self._client() as c:
            async def one(i):
                nonlocal done
                try:
                    out[i] = await self._get(c, f"/element-summary/{i}/", 2 * 3600)
                except Exception:
                    out[i] = {}
                done += 1
                if progress: progress(done, len(ids))
            await asyncio.gather(*(one(i) for i in ids))
        return out

    async def entry(self, team_id: int):
        async with self._client() as c:
            return await self._get(c, f"/entry/{team_id}/", 1800)

    async def entry_history(self, team_id: int):
        async with self._client() as c:
            return await self._get(c, f"/entry/{team_id}/history/", 900)

    async def entry_picks(self, team_id: int, gw: int):
        async with self._client() as c:
            return await self._get(c, f"/entry/{team_id}/event/{gw}/picks/", 3600)

    async def event_live(self, gw: int):
        async with self._client() as c:
            return await self._get(c, f"/event/{gw}/live/", 900)
