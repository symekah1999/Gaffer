-- Gaffer schema for Neon (Postgres). Safe to run repeatedly.
create table if not exists snapshots (
  id          bigserial primary key,
  created_at  timestamptz not null default now(),
  next_gw     int not null,
  picks_gw    int,
  source      text not null default 'live',
  gws         jsonb not null,
  players     jsonb not null,
  fixtures    jsonb not null,
  meta        jsonb not null
);

create table if not exists user_settings (
  user_id         uuid primary key,          -- Supabase auth user id
  team_id         int,
  free_transfers  int not null default 1,
  horizon         int not null default 5,
  updated_at      timestamptz not null default now()
);

-- Frozen pre-deadline projections per gameweek (kind: 'live' = made before the deadline,
-- 'backtest' = reconstructed using only data available before that gameweek).
create table if not exists predictions (
  gw        int not null,
  player_id int not null,
  xp        real not null,
  p_play    real,
  price     real,
  kind      text not null default 'live',
  made_at   timestamptz not null default now(),
  primary key (gw, player_id)
);

-- Actual FPL points per player per finished gameweek.
create table if not exists results (
  gw        int not null,
  player_id int not null,
  points    int not null,
  minutes   int not null,
  primary key (gw, player_id)
);

-- Model accuracy per gameweek across all players.
create table if not exists gw_accuracy (
  gw           int primary key,
  kind         text not null,
  n            int not null,
  mae          real,
  rmse         real,
  corr         real,
  top10_avg    real,
  field_avg    real,
  computed_at  timestamptz not null default now()
);

-- Published weekly report for a tracked FPL team.
create table if not exists team_reports (
  team_id     int not null,
  gw          int not null,
  data        jsonb not null,
  created_at  timestamptz not null default now(),
  primary key (team_id, gw)
);

-- Teams registered for weekly reports from inside the app (no GitHub setting needed).
create table if not exists tracked_teams (
  team_id   int primary key,
  added_at  timestamptz not null default now()
);
