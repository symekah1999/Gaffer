import { useState } from 'react'
import { api } from '../api.js'
import PlanView from '../components/PlanView.jsx'
import { Card, PageHead, Loading } from '../components/ui.jsx'
import { f1 } from '../util.js'

export default function MyTeam({ settings, save, session }) {
  const [teamId, setTeamId] = useState(settings.team_id || '')
  const [ft, setFt] = useState(settings.free_transfers)
  const [horizon, setHorizon] = useState(settings.horizon)
  const [wildcard, setWildcard] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState(null)
  const [sel, setSel] = useState(0)

  async function run(e) {
    e.preventDefault()
    setBusy(true); setErr(''); setRes(null)
    save({ team_id: teamId, free_transfers: Number(ft), horizon: Number(horizon) })
    try {
      const r = await api('/optimize/transfers', { team_id: Number(teamId), free_transfers: Number(ft), horizon: Number(horizon), max_transfers: 3, wildcard })
      setRes(r); setSel(r.recommended)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <PageHead title="My team" intro="Loads your current FPL squad and finds the transfers, lineup and captain with the most expected points. Extra transfers beyond your free ones are charged 4 points each." />
      <Card>
        <form className="form" onSubmit={run}>
          <label className="field">FPL team ID
            <input className="input" inputMode="numeric" pattern="[0-9]*" required value={teamId} onChange={(e) => setTeamId(e.target.value)} placeholder="e.g. 1234567" />
            <small>The number in the address bar when you open your Points page on the FPL site.</small>
          </label>
          <label className="field">Free transfers
            <select className="select" value={ft} onChange={(e) => setFt(e.target.value)}>{[0, 1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</select>
          </label>
          <label className="field">Plan ahead
            <select className="select" value={horizon} onChange={(e) => setHorizon(e.target.value)}>{[1, 3, 5, 8].map((n) => <option key={n} value={n}>{n} gameweek{n > 1 ? 's' : ''}</option>)}</select>
          </label>
          <label className="check"><input type="checkbox" checked={wildcard} onChange={(e) => setWildcard(e.target.checked)} /> Wildcard or Free Hit</label>
          <button className="btn" disabled={busy}>{busy ? 'Finding the best moves…' : 'Find best moves'}</button>
        </form>
        {!session && <p className="muted" style={{ marginTop: '.8rem', marginBottom: 0 }}>Sign in from the menu to keep these settings on all your devices and switch on weekly results.</p>}
      </Card>

      {busy && <Loading rows={2} />}
      {err && <Card><p className="error" role="alert" style={{ margin: 0 }}>{err}</p></Card>}

      {res && (
        <>
          <Card title="Your options" sub={`Bank £${f1(res.bank)}m · squad as of GW${res.picks_gw}`}>
            <div className="plans">
              {res.plans.map((p, i) => (
                <button key={i} type="button" className="plan" aria-pressed={sel === i} onClick={() => setSel(i)}>
                  <b>{p.k === 0 ? 'Keep squad' : `${p.k} transfer${p.k > 1 ? 's' : ''}`}</b>
                  <span className="gain">{p.gain > 0 ? '+' : ''}{f1(p.gain)}</span>
                  <small>xP vs keeping{p.hits ? ` · includes −${p.hits * 4} hit` : ''}</small>
                  {i === res.recommended && <span className="tag gold" style={{ justifySelf: 'start', marginTop: '.3rem' }}>Recommended</span>}
                </button>
              ))}
            </div>
          </Card>
          <PlanView plan={res.plans[sel]} showMoves />
        </>
      )}
    </div>
  )
}
