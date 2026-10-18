# Deploy Gaffer (Vercel + Neon + Supabase)

About 20 minutes. Do the steps in order.

## 1. Neon (database)
1. console.neon.tech > New project (pick the region closest to Vercel's, e.g. AWS eu-central or us-east).
2. Dashboard > Connect > copy the **pooled** connection string (host contains `-pooler`).
   It looks like `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require`.
3. Optional: run `db/schema.sql` in the SQL Editor. (The pipeline also creates the tables.)

## 2. Supabase (sign-in)
1. supabase.com > New project (a separate one from Growth OS / RentTrack keeps users apart).
2. Project Settings > API: copy the **Project URL** and the **anon public** key.
3. Authentication > Sign In / Providers: Email is on by default. Leave "Confirm email" on
   if friends will sign up; turn it off if it's just you.
   You only use Supabase for auth; no tables are needed there.

## 3. GitHub (code + scheduled data job)
1. Create an empty repo (e.g. `fpl-gaffer`), then from this folder:
   ```
   git init && git add . && git commit -m "Gaffer FPL planner"
   git branch -M main
   git remote add origin https://github.com/<you>/fpl-gaffer.git
   git push -u origin main
   ```
2. Repo > Settings > Secrets and variables > Actions > New repository secret:
   `DATABASE_URL` = the Neon pooled connection string.
3. Repo > Settings > Secrets and variables > Actions > Variables tab > New repository variable:
   `TRACK_TEAM_IDS` = your FPL team ID (several allowed, comma-separated). Signed-in users who save a
   team ID in the app are tracked automatically too.
4. Repo > Actions > "Update projections" > Run workflow. The first run takes longer (about 5-15 minutes)
   because it rebuilds predictions for every gameweek already played. Later runs take 3-6 minutes.
   Check the log ends with "Saved snapshot for GW..".
   It then runs by itself every 4 hours.

## 4. Vercel (app + API)
1. vercel.com > Add New > Project > import `fpl-gaffer`. Leave the framework as detected / "Other";
   `vercel.json` sets the build.
2. Environment variables (all environments):
   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Neon pooled connection string |
   | `SUPABASE_URL` | Supabase Project URL |
   | `SUPABASE_ANON_KEY` | Supabase anon public key |
   | `VITE_SUPABASE_URL` | same as SUPABASE_URL |
   | `VITE_SUPABASE_ANON_KEY` | same as SUPABASE_ANON_KEY |
3. Deploy. Open `https://<project>.vercel.app/api/status` and you should see `"state":"ready"`.
4. Back in Supabase > Authentication > URL Configuration: set **Site URL** to your Vercel URL
   (so confirmation emails link back to the app).

Every push to main redeploys Vercel. Changing a `VITE_` variable needs a redeploy to take effect.

## 5. Install on phone and desktop
Use "Install app" at the bottom of the menu, or:
- Android (Chrome): menu > Install app.
- iPhone (Safari): Share > Add to Home Screen.
- Windows / Mac (Chrome or Edge): the install icon in the address bar. Gaffer gets its own window,
  a Start menu / Dock icon, and right-click shortcuts to My team, Weekly results and Insights.

## Troubleshooting
- **Status says "No projections yet"**: run the GitHub workflow (step 3.4).
- **Weekly results says "not tracked yet"**: add the team to TRACK_TEAM_IDS, or sign in and save it,
  then run the workflow (or wait up to 4 hours).
- **First run stopped before all old gameweeks were rebuilt**: it does 12 per run and continues next run.
- **Workflow log shows 403 from fantasy.premierleague.com**: FPL is blocking GitHub's servers. Run the
  pipeline from your own PC instead (`python -m pipeline.run` with DATABASE_URL set), or on a schedule
  with Windows Task Scheduler.
- **"My team" says the FPL site returned an error**: the same blocking, but for Vercel's servers. Tell me
  and I'll move team loading into the browser or the pipeline.
- **Scheduled runs stopped**: GitHub pauses schedules on repos with no activity for 60 days. Re-enable
  it in the Actions tab.
- **Demo mode**: add a repository variable (not secret) `FPL_MOCK` = `1` and rerun the workflow.
  Delete it to return to real data.
