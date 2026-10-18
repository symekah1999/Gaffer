import { Crown, Trophy, Sparkles, TriangleAlert, Gauge } from 'lucide-react'
import { useApi, useNow } from '../hooks.js'
import { Card, PlayerRow, Loading, Stat } from '../components/ui.jsx'
import { LineChart } from '../components/Charts.jsx'
import { countdown, localTime, f1, int, signed } from '../util.js'

function LastWeek({ teamId, openConnect }) {
  const r = useApi(teamId ? `/reports?team_id=${teamId}` : null)
  if (!teamId) return (
    <Card title="Your last gameweek" icon={Trophy}>
      <p className="muted">Connect your FPL team to see your weekly score against Gaffer's predictions here.</p>
      <button className="btn" onClick={openConnect}>Connect my team</button>
    </Card>
  )
  if (r.loading) return <div className="skeleton" />
  const w = r.data?.weeks?.at(-1)
  if (!w) return (
    <Card title="Your last gameweek" icon={Trophy}>
      <p className="muted">{r.data?.tracked ? 'Your first weekly report appears after the next data update.' : 'Sign in and save your team ID to switch on weekly results.'}</p>
      <a className="more" href="#/results">How weekly results work</a>
    </Card>
  )
  const d = w.points - w.predicted
  return (
    <Card title={`GW${w.gw} result`} icon={Trophy} sub={w.team_name} action={<a className="more" href="#/results">All weeks</a>}>
      <div className="stats">
        <Stat value={w.points} label="your points" />
        <Stat value={f1(w.predicted)} label="Gaffer predicted" />
        <Stat value={signed(d)} tone={d >= 0 ? 'up' : 'down'} label="vs prediction" />
        <Stat value={w.gaffer_actual} label="Gaffer's lineup would have scored" />
      </div>
      {w.gw_rank && <p className="muted" style={{ marginTop: '.8rem' }}>Gameweek rank {int(w.gw_rank)} · overall {int(w.overall_rank)}</p>}
    </Card>
  )
}

export default function Home({ status, settings, openConnect }) {
  const now = useNow(30000)
  const ins = useApi('/insights')
  const i = ins.data
  const track = i?.track || []
  return (
    <div className="stack">
      <section className="hero">
        <div className="gwlabel">Gameweek {status.next_gw} deadline</div>
        <div className="count">{status.next_deadline ? countdown(status.next_deadline, now) : '–'}</div>
        <div className="when">{status.next_deadline && localTime(status.next_deadline)}</div>
        <div className="actions">
          <a className="btn" href="#/team">Plan my transfers</a>
          <a className="btn ghost" href="#/insights">See insights</a>
        </div>
      </section>

      {ins.loading ? <Loading rows={2} /> : i && (
        <div className="grid">
          <Card title="Captain picks" icon={Crown} sub={`Expected points for GW${status.next_gw}`} action={<a className="more" href="#/insights">More</a>}>
            <ul className="list">{i.captains.slice(0, 3).map((p) => <PlayerRow key={p.id} p={p} value={p.xp_next} sub="xP" max={i.captains[0].xp_next} />)}</ul>
          </Card>
          <LastWeek teamId={settings.team_id} openConnect={openConnect} />
          <Card title="Differentials" icon={Sparkles} sub="Under 8% owned, next 3 gameweeks">
            <ul className="list">{i.differentials.slice(0, 3).map((p) => <PlayerRow key={p.id} p={p} value={p.xp3} sub="xP" />)}</ul>
          </Card>
          <Card title="Injury watch" icon={TriangleAlert} sub="Popular players with a doubt">
            {i.injuries.length ? <ul className="list">{i.injuries.slice(0, 4).map((p) => <PlayerRow key={p.id} p={p} value={`${Math.round(p.p_play * 100)}%`} sub="chance" />)}</ul>
              : <p className="muted">No major doubts among popular players.</p>}
          </Card>
          {track.length > 0 && (
            <Card title="Track record" icon={Gauge} sub="Points scored by Gaffer's top 10 picks each week vs the average player" action={<a className="more" href="#/model">Details</a>} className="span">
              <LineChart labels={track.map((t) => `GW${t.gw}`)} height={180} series={[
                { name: "Gaffer's top 10", values: track.map((t) => t.top10_avg), color: 'var(--turf)' },
                { name: 'Average player', values: track.map((t) => t.field_avg), color: 'var(--muted)', dashed: true },
              ]} />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
