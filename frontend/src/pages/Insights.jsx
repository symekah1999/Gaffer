import { useState } from 'react'
import { Crown, Sparkles, Coins, Flame, Snowflake, Swords, Shield, TriangleAlert, Users } from 'lucide-react'
import { useApi } from '../hooks.js'
import { Card, PageHead, PlayerRow, Loading, ErrorBox, Seg } from '../components/ui.jsx'
import { f1 } from '../util.js'

function Runs({ rows, metric, label }) {
  return (
    <ul className="list">
      {rows.map((r) => (
        <li key={r.team} className="prow">
          <span className="badge">{r.team}</span>
          <div style={{ minWidth: 0 }}><div className="chips">{r.games.map((g, i) => <span key={i} className="chip">{g}</span>)}</div></div>
          <div className="pval">{f1(r[metric])}<small>{label}</small></div>
        </li>
      ))}
    </ul>
  )
}

export default function Insights({ status }) {
  const { data: i, error, loading, reload } = useApi('/insights')
  const [pos, setPos] = useState('MID')
  if (loading) return <Loading rows={4} />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const g = i.gws
  return (
    <div className="stack">
      <PageHead title="Insights" intro={`What the model sees ahead of GW${status.next_gw}. xP means expected points.`} />
      <div className="grid two">
        <Card title="Captaincy" icon={Crown} sub={`Highest expected points for GW${g[0]} (before doubling)`}>
          <ul className="list">{i.captains.map((p) => <PlayerRow key={p.id} p={p} value={p.xp_next} sub="xP" max={i.captains[0].xp_next} />)}</ul>
        </Card>
        <Card title="Differentials" icon={Sparkles} sub={`Under 8% owned, best over GW${g[0]}–${g[2]}`}>
          <ul className="list">{i.differentials.map((p) => <PlayerRow key={p.id} p={p} value={p.xp3} sub="xP" />)}</ul>
        </Card>
        <Card title="Best value" icon={Coins} sub="Expected points per £m over the next 5 gameweeks"
          action={<Seg label="Position" value={pos} onChange={setPos} options={[['GKP', 'GK'], ['DEF', 'DEF'], ['MID', 'MID'], ['FWD', 'FWD']]} />}>
          <ul className="list">{i.value[pos].map((p) => <PlayerRow key={p.id} p={p} value={`£${f1(p.price)}m`} sub={`${f1(p.xp5 / p.price)} xP per £m`} />)}</ul>
        </Card>
        <Card title="Template check" icon={Users} sub="Most-owned players and what they are expected to score">
          <ul className="list">{i.template.map((p) => <PlayerRow key={p.id} p={p} value={p.xp_next} sub="xP" />)}</ul>
        </Card>
        <Card title="Running hot" icon={Flame} sub="Recent form well above what the underlying numbers support. Likely to cool.">
          {i.hot.length ? <ul className="list">{i.hot.map((p) => <PlayerRow key={p.id} p={p} value={f1(p.form)} sub={`form vs ${f1(p.xp_next)} xP`} />)}</ul> : <p className="muted">No big overperformers right now.</p>}
        </Card>
        <Card title="Due a return" icon={Snowflake} sub="Underlying numbers point to more points than recent form shows.">
          {i.cold.length ? <ul className="list">{i.cold.map((p) => <PlayerRow key={p.id} p={p} value={f1(p.xp_next)} sub={`xP vs ${f1(p.form)} form`} />)}</ul> : <p className="muted">No clear bounce-back candidates.</p>}
        </Card>
        <Card title="Best fixtures for attackers" icon={Swords} sub={`Goals each team should score, GW${g[0]}–${g[3]}`}>
          <Runs rows={i.attack_runs} metric="att" label="goals" />
        </Card>
        <Card title="Best fixtures for defenders" icon={Shield} sub={`Goals each team should concede, GW${g[0]}–${g[3]}`}>
          <Runs rows={i.defence_runs} metric="dfn" label="conceded" />
        </Card>
        <Card title="Injury and suspension watch" icon={TriangleAlert} sub="Owned by at least 2% of managers">
          {i.injuries.length ? (
            <ul className="list">{i.injuries.map((p) => (
              <li key={p.id} className="prow">
                <span className="badge">{p.team}</span>
                <div style={{ minWidth: 0 }}><div className="pname">{p.name}</div><div className="pmeta" style={{ whiteSpace: 'normal' }}>{p.news || 'Fitness doubt'} · {f1(p.selected)}% owned</div></div>
                <div className="pval"><span className={'tag ' + (p.p_play === 0 ? 'warn' : '')}>{Math.round(p.p_play * 100)}%</span></div>
              </li>))}
            </ul>) : <p className="muted">No major doubts among popular players.</p>}
        </Card>
      </div>
    </div>
  )
}
