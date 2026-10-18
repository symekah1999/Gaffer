import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CalendarClock, Sparkles } from 'lucide-react'
import { api } from '../api.js'
import PlanView from '../components/PlanView.jsx'
import { Card, PageHead, Loading, Stat } from '../components/ui.jsx'
import { f1 } from '../util.js'

function pair(w) {
  const ins = [...w.transfers_in]
  return w.transfers_out.map((o) => { const k = ins.findIndex((x) => x.pos === o.pos); return [o, ins.splice(k >= 0 ? k : 0, 1)[0]] })
}

function Timeline({ plan }) {
  return (
    <ol className="timeline">
      {plan.weeks.map((w) => (
        <li key={w.gw}>
          <div className="tl-head">
            <b>GW{w.gw}</b>
            <span className="tag plain">{w.ft} free transfer{w.ft === 1 ? '' : 's'}</span>
            {w.hits > 0 && <span className="tag warn">−{w.hits * 4} hit</span>}
            <span className="tl-pts">{f1(w.points)} xP · captain {w.captain}</span>
          </div>
          {w.transfers_in.length === 0 ? (
            <p className="muted tl-move">{w.ft >= 5 ? 'No transfer (already holding the maximum of 5)' : 'Save your transfer for next week'}</p>
          ) : (
            <ul className="tl-moves">
              {pair(w).map(([o, n]) => (
                <li key={o.id}><span className="out">{o.name}</span><ArrowRight size={14} aria-label="to" /><span className="in">{n?.name}</span><small>{n?.team} · £{f1(n?.price)}m</small></li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  )
}

function Chips({ teamId }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/chips?team_id=${teamId}`).then(setD).catch((e) => setErr(e.message)) }, [teamId])
  if (err) return <Card title="Chip planner" icon={Sparkles}><p className="error">{err}</p></Card>
  if (!d) return <div className="skeleton" />
  const note = (c) => c.chip === '3xc' ? `captain ${c.player}` : c.chip === 'bboost' ? 'your bench' : 'a one-week dream team'
  return (
    <Card title="Chip planner" icon={Sparkles} sub="The best gameweek for each chip you still have, based on your current squad">
      <ul className="list">
        {d.chips.filter((c) => c.chip !== 'wildcard').map((c) => (
          <li key={c.chip} className="prow">
            <span className="badge">{c.chip === '3xc' ? 'TC' : c.chip === 'bboost' ? 'BB' : 'FH'}</span>
            <div style={{ minWidth: 0 }}>
              <div className="pname">{c.label}</div>
              <div className="pmeta" style={{ whiteSpace: 'normal' }}>{c.best_gw ? `Best in GW${c.best_gw}, ${note(c)}` : 'Already used this half of the season'}</div>
            </div>
            <div className="pval">{c.gain != null ? `+${f1(c.gain)}` : '–'}<small>{c.gain != null ? 'extra xP' : ''}</small></div>
          </li>
        ))}
      </ul>
      {d.weeks.some((w) => w.doubles || w.blanks) && (
        <p className="muted" style={{ marginTop: '.6rem' }}>{d.weeks.filter((w) => w.doubles || w.blanks).map((w) => `GW${w.gw}: ${w.doubles ? `${w.doubles} teams play twice` : ''}${w.doubles && w.blanks ? ', ' : ''}${w.blanks ? `${w.blanks} teams blank` : ''}`).join(' · ')}</p>
      )}
      <p className="note" style={{ marginTop: '.6rem' }}>Bench Boost and Triple Captain are worth most in double gameweeks; Free Hit in blank gameweeks. {d.chips.find((c) => c.chip === 'wildcard')?.available ? 'Your Wildcard is still available.' : ''} Gains are measured against your current squad, before planned transfers.</p>
    </Card>
  )
}

export default function MyTeam({ settings, save, session, team, openConnect }) {
  const teamId = settings.team_id
  const [ft, setFt] = useState(settings.free_transfers)
  const [ftNote, setFtNote] = useState('')
  const [horizon, setHorizon] = useState(settings.horizon)
  const [wildcard, setWildcard] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState(null)
  const [sel, setSel] = useState(0)

  async function run(e, ftOverride) {
    e?.preventDefault()
    const useFt = ftOverride ?? ft
    setBusy(true); setErr(''); setRes(null)
    save({ free_transfers: Number(useFt), horizon: Number(horizon) })
    try {
      const r = await api('/optimize/transfers', { team_id: Number(teamId), free_transfers: Number(useFt), horizon: Number(horizon), max_transfers: 3, wildcard })
      setRes(r); setSel(r.recommended)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  const auto = useRef(false)
  useEffect(() => {
    if (!teamId || auto.current) return
    auto.current = true
    api(`/team/state?team_id=${teamId}`).then((st) => {
      if (st.free_transfers_estimate != null) {
        setFt(st.free_transfers_estimate)
        setFtNote(`Estimated from your FPL history: ${st.free_transfers_estimate}. Change it if that's wrong.`)
        run(null, st.free_transfers_estimate)
      } else run()
    }).catch(() => run())
  }, [teamId])

  const plan = res?.plan
  return (
    <div className="stack">
      <PageHead title="My team" intro="Your transfers, captain and chips, planned week by week to get the most points from your squad." />
      <Card>
        <form className="form" onSubmit={run}>
          <div className="field">Your team
            <div className="connected">
              <b>{teamId ? (team?.name || `Team ${teamId}`) : 'Not connected'}</b>
              <button type="button" className="linkbtn" onClick={openConnect}>{teamId ? 'Change' : 'Connect your team'}</button>
            </div>
          </div>
          <label className="field">Free transfers
            <select className="select" value={ft} onChange={(e) => { setFt(e.target.value); setFtNote('') }}>{[0, 1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</select>
          </label>
          <label className="field">Plan ahead
            <select className="select" value={horizon} onChange={(e) => setHorizon(e.target.value)}>{[3, 5, 6].map((n) => <option key={n} value={n}>{n} gameweeks</option>)}</select>
          </label>
          <label className="check"><input type="checkbox" checked={wildcard} onChange={(e) => setWildcard(e.target.checked)} /> Playing Wildcard or Free Hit</label>
          <button className="btn" disabled={busy || !teamId}>{busy ? 'Planning…' : 'Plan my moves'}</button>
        </form>
        {ftNote && <p className="muted" style={{ margin: '.7rem 0 0' }}>{ftNote}</p>}
      </Card>

      {busy && <Loading rows={2} />}
      {err && <Card><p className="error" role="alert" style={{ margin: 0 }}>{err}</p></Card>}

      {res && plan && (
        <>
          <Card title={`Your ${plan.weeks.length}-week plan`} icon={CalendarClock}
            sub="When to transfer, when to save a free transfer, and when a hit is worth it. Hits are only taken when they clearly pay back.">
            <div className="stats" style={{ marginBottom: '1rem' }}>
              <Stat value={`+${f1(plan.gain)}`} tone={plan.gain > 0 ? 'up' : ''} label={`expected points vs making no transfers (${f1(plan.keep_total)})`} />
              <Stat value={plan.hits ? `−${plan.hits * 4}` : '0'} label="points spent on hits" />
              <Stat value={plan.ft_end} label={`free transfers left after GW${plan.weeks.at(-1).gw}`} />
            </div>
            <Timeline plan={plan} />
            <p className="muted" style={{ marginTop: '.8rem', marginBottom: 0 }}>Make only this week's moves now. Run the plan again next week, because team news and form will have changed.</p>
          </Card>
          <Chips teamId={teamId} />
          <PlanView plan={plan} showMoves />
          <details className="card">
            <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Compare: only planning this week</summary>
            <div className="plans" style={{ marginTop: '.9rem' }}>
              {res.plans.map((p, i) => (
                <button key={i} type="button" className="plan" aria-pressed={sel === i} onClick={() => setSel(i)}>
                  <b>{p.k === 0 ? 'Keep squad' : `${p.k} transfer${p.k > 1 ? 's' : ''}`}</b>
                  <span className="gain">{p.gain > 0 ? '+' : ''}{f1(p.gain)}</span>
                  <small>xP vs keeping{p.hits ? ` · includes −${p.hits * 4} hit` : ''}</small>
                </button>
              ))}
            </div>
          </details>
        </>
      )}
      {res && !plan && <PlanView plan={res.plans[sel]} showMoves />}
    </div>
  )
}
