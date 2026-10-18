import { useState } from 'react'
import { api } from '../api.js'
import PlanView from '../components/PlanView.jsx'
import { Card, PageHead, Loading } from '../components/ui.jsx'

export default function Builder({ settings }) {
  const [budget, setBudget] = useState(100)
  const [horizon, setHorizon] = useState(settings.horizon || 5)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [plan, setPlan] = useState(null)

  async function run(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try { setPlan(await api('/optimize/squad', { budget: Number(budget), horizon: Number(horizon) })) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <PageHead title="Squad builder" intro="The best 15 players from scratch, within budget and at most 3 per club. Useful for a wildcard, Free Hit or a new team." />
      <Card>
        <form className="form" onSubmit={run}>
          <label className="field">Budget (£m)<input className="input" type="number" step="0.1" min="80" max="120" value={budget} onChange={(e) => setBudget(e.target.value)} /></label>
          <label className="field">Plan ahead
            <select className="select" value={horizon} onChange={(e) => setHorizon(e.target.value)}>{[1, 3, 5, 8].map((n) => <option key={n} value={n}>{n} gameweek{n > 1 ? 's' : ''}</option>)}</select>
          </label>
          <button className="btn" disabled={busy}>{busy ? 'Building…' : 'Build best squad'}</button>
        </form>
      </Card>
      {busy && <Loading rows={2} />}
      {err && <Card><p className="error" role="alert" style={{ margin: 0 }}>{err}</p></Card>}
      {plan && !busy && <PlanView plan={plan} />}
    </div>
  )
}
