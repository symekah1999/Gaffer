# Gaffer: FPL planner

Expected points for every FPL player over the next 8 gameweeks, the best squad, XI, captain and
transfers, insights, and a weekly report comparing your real FPL score with Gaffer's predictions.
Installs as an app on phone and desktop.

## Pages
- Dashboard: deadline countdown, captain picks, your last gameweek, differentials, injuries, track record.
- My team: best 0-3 transfer options for your squad (hits priced in), lineup and captain.
- Weekly results: your actual points vs predicted every gameweek, what Gaffer's lineup from your squad
  would have scored, captain comparison, player-by-player detail. CSV and PDF export.
- Insights: captaincy, differentials, value by position, running hot / due a return, fixture runs,
  template check, injury watch.
- Players, Fixtures, Squad builder, Model & accuracy (season track record).

## How it fits together
- **GitHub Actions** (`pipeline/`) runs every 4 hours: downloads FPL data, runs the projection model
  (team ratings, player rates, minutes, LightGBM correction), saves a snapshot to Neon, freezes the
  pre-deadline predictions for the next gameweek, and after each finished gameweek publishes results:
  model accuracy and a report for every tracked team. Gameweeks played before tracking started are
  rebuilt from data available before each deadline.
- **Neon** (`db/schema.sql`) stores snapshots, frozen predictions, actual results, accuracy, weekly team
  reports and user settings.
- **Vercel** hosts the React app (`frontend/`) and a lightweight Python API (`api/main.py`) that reads
  the latest snapshot and runs the squad/transfer optimiser (HiGHS solver, about 1 second).
- **Supabase** handles sign-in so your team ID and settings follow you across devices.
  Signing in is optional; everything else works without an account.

Setup: see DEPLOY.md.

## Vercel setup
One Vercel project with two services (see `vercel.json`): `frontend` (Vite, served at `/`) and `api`
(FastAPI, served at `/api/*`). The data pipeline is not a Vercel service; it runs in GitHub Actions.
The services don't call each other, so no bindings are needed.

## Local development
```
# once
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r api/requirements.txt -r pipeline/requirements.txt uvicorn
cd frontend && npm install && cd ..

# fill the database (FPL_MOCK=1 for simulated data)
export DATABASE_URL="postgresql://..."                       # Windows: $env:DATABASE_URL="postgresql://..."
python -m pipeline.run

# run the API and the app
(cd api && uvicorn main:app --port 8000 --reload)
cd frontend && npm run dev                                   # http://localhost:5173
```
For sign-in locally, copy `frontend/.env.example` to `frontend/.env.local` and fill it in, and set
SUPABASE_URL / SUPABASE_ANON_KEY for the API.

## Limits
- Free transfers are entered by you (the public FPL API does not expose them).
- Selling prices are estimated from your transfer history (half of price rises, rounded down).
- Your squad is read as of the last deadline; transfers made since are not visible yet.
- Team news from press conferences is only reflected once FPL updates player status.
- Rebuilt (backtest) weeks don't know that week's injury news, so they are a little less accurate.
- The last automatic run before a deadline can be up to 4 hours early; late team news after that is missed.
- Tested end to end on simulated data with Postgres and a headless browser; not yet run against the live FPL API.
