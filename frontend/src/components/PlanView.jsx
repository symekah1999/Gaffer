import { ArrowRight } from 'lucide-react'
import Pitch from './Pitch.jsx'
import { Card, Stat } from './ui.jsx'
import { f1, sum } from '../util.js'

export function GwBars({ plan }) {
  const max = Math.max(...plan.gw_points, 1)
  return (
    <div className="gwbars" role="img" aria-label="Expected points by gameweek">
      {plan.gw_points.map((v, i) => (
        <div key={i} className="gwbar">
          <span className="gwv">{f1(v)}</span>
          <div className="gwcol"><div style={{ height: `${(v / max) * 100}%` }} /></div>
          <span className="gwl">GW{plan.gws[i]}</span>
        </div>
      ))}
    </div>
  )
}

function Moves({ plan }) {
  if (!plan.transfers_in.length) return <p className="muted">No transfers. Keep your squad and play the lineup below.</p>
  const ins = [...plan.transfers_in]
  const pairs = plan.transfers_out.map((o) => { const k = ins.findIndex((x) => x.pos === o.pos); return [o, ins.splice(k >= 0 ? k : 0, 1)[0]] })
  return (
    <ul className="moves">
      {pairs.map(([o, n]) => (
        <li key={o.id}>
          <span className="out">{o.name} <small>{o.team} · £{f1(o.buy_price)}m</small></span>
          <ArrowRight size={16} className="muted" aria-label="replaced by" />
          <span className="in">{n?.name} <small>{n?.team} · £{f1(n?.price)}m</small></span>
          <span className="tag">{n ? `+${f1(sum(n.xp) - sum(o.xp))} xP` : ''}</span>
        </li>
      ))}
    </ul>
  )
}

export default function PlanView({ plan, showMoves }) {
  const cap = plan.xi.find((p) => p.id === plan.captain)
  return (
    <>
      <Card>
        <div className="stats" style={{ marginBottom: '1.1rem' }}>
          <Stat value={f1(plan.net_total)} label={`expected points over ${plan.gws.length} GW${plan.gws.length > 1 ? 's' : ''}${plan.hits ? ` (after −${plan.hits * 4} hit)` : ''}`} />
          <Stat value={`£${f1(plan.cost)}m`} label="squad value" />
          <Stat value={cap?.name} label={`captain for GW${plan.gw} · ${f1(cap?.xp_next)} xP`} />
        </div>
        <GwBars plan={plan} />
      </Card>
      {showMoves && <Card title="Transfers"><Moves plan={plan} /></Card>}
      <Card title={`Best XI for GW${plan.gw}`} sub="Captain marked C, vice-captain V. A red dot means a fitness doubt."><Pitch plan={plan} /></Card>
    </>
  )
}
