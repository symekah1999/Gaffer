import { f1 } from '../util.js'

function Marker({ p, captain, vice }) {
  const flagged = p.status !== 'a' || p.p_play < 1
  return (
    <div className="marker" title={p.news || undefined}>
      <div className="shirt">
        <span>{p.team}</span>
        {captain && <b className="armband">C</b>}
        {vice && <b className="armband vice">V</b>}
        {flagged && <i className="flag" aria-label="Fitness doubt" />}
      </div>
      <div className="mname">{p.name}</div>
      <div className="mxp">{f1(p.xp_next)} <small>{p.fixture}</small></div>
    </div>
  )
}

export default function Pitch({ plan }) {
  return (
    <div className="pitch-wrap">
      <div className="pitch">
        <svg className="lines" viewBox="0 0 100 120" preserveAspectRatio="none" aria-hidden="true">
          <g fill="none" stroke="rgba(255,255,255,.5)" strokeWidth=".5">
            <rect x="3" y="3" width="94" height="114" /><line x1="3" y1="60" x2="97" y2="60" /><circle cx="50" cy="60" r="10" />
            <rect x="26" y="3" width="48" height="16" /><rect x="38" y="3" width="24" height="6" />
            <rect x="26" y="101" width="48" height="16" /><rect x="38" y="111" width="24" height="6" />
          </g>
        </svg>
        {[4, 3, 2, 1].map((pos) => (
          <div className="pline" key={pos}>
            {plan.xi.filter((p) => p.pos === pos).map((p) => <Marker key={p.id} p={p} captain={p.id === plan.captain} vice={p.id === plan.vice} />)}
          </div>
        ))}
      </div>
      <div className="bench"><span className="bench-label">Bench</span>{plan.bench.map((p) => <Marker key={p.id} p={p} />)}</div>
    </div>
  )
}
