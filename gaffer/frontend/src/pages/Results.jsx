import { useState } from 'react'
import { ChevronDown, ChevronRight, Download, Printer } from 'lucide-react'
import { useApi } from '../hooks.js'
import { Card, PageHead, Stat, Loading, ErrorBox } from '../components/ui.jsx'
import { LineChart } from '../components/Charts.jsx'
import { downloadCSV, f1, int, signed, sum } from '../util.js'

const POS = { 1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD' }

function Week({ w, open, onToggle }) {
  const d = w.points - w.predicted
  const gx = new Set(w.gaffer_xi)
  const rows = [...w.players].sort((a, b) => (b.mult > 0) - (a.mult > 0) || a.pos - b.pos || b.pts - a.pts)
  return (
    <div className="week">
      <button className="week-row" onClick={onToggle} aria-expanded={open}>
        <span className="gwn">GW{w.gw}{w.kind === 'backtest' && <><br /><span className="tag plain" title="Predictions rebuilt from data available before this gameweek">Rebuilt</span></>}</span>
        <span><span className="v">{w.points}</span><span className="l">your points</span></span>
        <span><span className="v">{f1(w.predicted)}</span><span className="l">predicted</span></span>
        <span><span className={'v diff ' + (d >= 0 ? 'up' : 'down')}>{signed(d)}</span><span className="l">difference</span></span>
        {open ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
      </button>
      {open && (
        <div className="week-body">
          <div className="chips">
            {w.chip && <span className="tag gold">{w.chip.replace('_', ' ')}</span>}
            {w.gw_rank && <span className="chip">GW rank {int(w.gw_rank)}</span>}
            {w.overall_rank && <span className="chip">Overall {int(w.overall_rank)}</span>}
            {w.transfer_cost > 0 && <span className="chip">−{w.transfer_cost} transfer cost</span>}
            {w.bench_points != null && <span className="chip">{w.bench_points} on bench</span>}
          </div>
          <div className="stats">
            <Stat value={`${w.captain?.name ?? '–'} · ${w.captain ? w.captain.pts * w.captain.mult : '–'}`} label={`your captain (predicted ${f1((w.captain?.xp || 0) * (w.captain?.mult || 2))})`} />
            <Stat value={`${w.gaffer_captain?.name ?? '–'} · ${w.gaffer_captain ? w.gaffer_captain.pts * 2 : '–'}`} label="Gaffer's captain from your squad" />
            <Stat value={`${w.gaffer_actual} vs ${w.lineup_actual}`} tone={w.gaffer_actual > w.lineup_actual ? 'up' : ''} label="Gaffer's lineup vs yours, before auto-subs" />
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr><th>Player</th><th>Pos</th><th className="num">Predicted</th><th className="num">Actual</th><th className="num">Mins</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className={p.mult === 0 ? 'benched' : ''}>
                    <td><b>{p.name}</b> <small>{p.team}</small>{p.is_captain && <span className="cap">C</span>}{gx.has(p.id) && <span className="gx" title="In Gaffer's XI">G</span>}</td>
                    <td>{POS[p.pos]}</td>
                    <td className="num">{f1(p.xp)}</td>
                    <td className="num"><b>{p.pts}</b></td>
                    <td className="num">{p.minutes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ fontSize: '.82rem' }}>Greyed rows were on your bench. G marks players Gaffer would have started. Points per player are before the captain multiplier.</p>
        </div>
      )}
    </div>
  )
}

export default function Results({ settings, session, save }) {
  const [input, setInput] = useState(settings.team_id || '')
  const [teamId, setTeamId] = useState(settings.team_id || '')
  const [open, setOpen] = useState(null)
  const [msg, setMsg] = useState('')
  const r = useApi(teamId ? `/reports?team_id=${teamId}` : null)
  const weeks = r.data?.weeks || []

  const pick = (e) => { e.preventDefault(); setTeamId(input.trim()); setOpen(null) }
  const exportCSV = () => downloadCSV(`gaffer-results-${teamId}.csv`, weeks, [
    ['Gameweek', (w) => w.gw], ['Points', (w) => w.points], ['Predicted', (w) => w.predicted], ['Difference', (w) => f1(w.points - w.predicted)],
    ["Gaffer lineup (actual)", (w) => w.gaffer_actual], ['Your lineup before auto-subs', (w) => w.lineup_actual],
    ['Captain', (w) => w.captain?.name], ['Captain points', (w) => w.captain ? w.captain.pts * w.captain.mult : ''],
    ['Gaffer captain', (w) => w.gaffer_captain?.name], ['GW rank', (w) => w.gw_rank], ['Overall rank', (w) => w.overall_rank],
    ['Chip', (w) => w.chip || ''], ['Prediction type', (w) => (w.kind === 'backtest' ? 'rebuilt' : 'pre-deadline')],
  ])
  const track = () => { save({ team_id: teamId }); setMsg('Tracking switched on. Your past gameweeks are published at the next data update (within 4 hours).') }

  const totals = weeks.length && {
    pts: sum(weeks.map((w) => w.points)), pred: sum(weeks.map((w) => w.predicted)),
    gaffer: sum(weeks.map((w) => w.gaffer_actual - w.lineup_actual)),
    capWins: weeks.filter((w) => w.captain && w.gaffer_captain && w.gaffer_captain.pts > w.captain.pts).length,
    best: weeks.reduce((a, b) => (b.points > a.points ? b : a)),
  }
  const ordered = [...weeks].reverse()

  return (
    <div className="stack">
      <PageHead title="Weekly results" intro="After every gameweek, your real FPL score is published next to what Gaffer predicted for your lineup, and what Gaffer's own lineup from your squad would have scored."
        actions={weeks.length > 0 && <>
          <button className="btn secondary" onClick={exportCSV}><Download size={16} /> CSV</button>
          <button className="btn secondary" onClick={() => window.print()}><Printer size={16} /> Print or PDF</button>
        </>} />

      <Card className="no-print">
        <form className="form" onSubmit={pick}>
          <label className="field">FPL team ID<input className="input" inputMode="numeric" pattern="[0-9]*" required value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. 1234567" /></label>
          <button className="btn">Show results</button>
        </form>
      </Card>

      {r.loading && <Loading rows={2} />}
      {r.error && <ErrorBox error={r.error} onRetry={r.reload} />}
      {r.data && !weeks.length && (
        <Card>
          <div className="empty">
            <h2>{r.data.tracked ? 'Waiting for the next update' : 'This team is not tracked yet'}</h2>
            {r.data.tracked
              ? <p>Weekly results for this team appear after the next data update, usually within 4 hours. Every finished gameweek this season is included.</p>
              : session
                ? <><p>Track this team and Gaffer will publish every gameweek this season, then a new report after each gameweek.</p><button className="btn" onClick={track}>Track team {teamId}</button></>
                : <p>Sign in from the menu, then save this team ID to switch on weekly results.</p>}
            {msg && <p className="muted" style={{ marginTop: '.8rem' }}>{msg}</p>}
          </div>
        </Card>
      )}

      {weeks.length > 0 && (
        <>
          <Card title={r.data.team_name} sub={`${r.data.manager} · ${weeks.length} gameweeks`}>
            <div className="stats">
              <Stat value={totals.pts} label="season points" />
              <Stat value={f1(totals.pred)} label="Gaffer predicted for your lineups" />
              <Stat value={f1(totals.pts / weeks.length)} label={`average per week (predicted ${f1(totals.pred / weeks.length)})`} />
              <Stat value={signed(totals.gaffer)} tone={totals.gaffer >= 0 ? 'up' : 'down'} label="points Gaffer's lineups would have added" />
              <Stat value={`GW${totals.best.gw} · ${totals.best.points}`} label="best week" />
              <Stat value={`${totals.capWins} of ${weeks.length}`} label="weeks Gaffer's captain beat yours" />
            </div>
          </Card>
          <Card title="Points by gameweek">
            <LineChart labels={weeks.map((w) => `GW${w.gw}`)} series={[
              { name: 'Your points', values: weeks.map((w) => w.points), color: 'var(--turf)' },
              { name: 'Predicted', values: weeks.map((w) => w.predicted), color: 'var(--bib)', dashed: true },
              { name: "Gaffer's lineup", values: weeks.map((w) => w.gaffer_actual), color: 'var(--muted)' },
            ]} />
          </Card>
          <Card title="Every gameweek" sub="Tap a week to see each player's predicted and actual points.">
            {ordered.map((w) => <Week key={w.gw} w={w} open={open === w.gw} onToggle={() => setOpen(open === w.gw ? null : w.gw)} />)}
          </Card>
          {weeks.some((w) => w.kind === 'backtest') && (
            <p className="note">Weeks marked Rebuilt were played before Gaffer was tracking your team. Their predictions were rebuilt using only results and data available before that deadline, without that week's injury news, so they are slightly less accurate than live pre-deadline predictions.</p>
          )}
        </>
      )}
    </div>
  )
}
