import { Card } from './ui.jsx'
import { LineChart } from './Charts.jsx'
import { f1, int } from '../util.js'

const USED = ['gaffer:0.3+plan', 'gaffer:0.3']

export default function SeasonSim({ bt }) {
  if (!bt?.engines) return null
  const rows = Object.entries(bt.engines).map(([k, v]) => ({ k, ...v })).sort((a, b) => b.average - a.average)
  const used = USED.find((k) => bt.engines[k])
  const pick = [used, 'fpl_xp', 'form'].filter((k) => bt.engines[k])
  const cum = (w) => w.reduce((a, x) => [...a, (a.at(-1) || 0) + x.points], [])
  const season = bt.season.replace('-', '/')
  return (
    <Card title={`Season simulation: ${season}`}
      sub={`Gaffer managed a team through the whole ${season} season using only what was known before each deadline, after training on ${bt.trained_on.map((s) => s.replace('-', '/')).join(', ')}.`}>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Strategy</th><th className="num">Points per week</th><th className="num">Season total</th><th className="num">Hits taken</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.k}>
              <td><b>{r.label}</b>{r.k === used && <> <span className="tag">Used in the app</span></>}</td>
              <td className="num"><b>{f1(r.average)}</b></td><td className="num">{int(r.total)}</td><td className="num">{r.hits}</td>
            </tr>))}
          </tbody>
        </table>
      </div>
      <h3 style={{ marginTop: '1.2rem' }}>Points through the season</h3>
      <LineChart labels={bt.engines[pick[0]].weeks.map((w) => `GW${w.gw}`)} series={pick.map((k, i) => ({
        name: bt.engines[k].label, values: cum(bt.engines[k].weeks),
        color: ['var(--turf)', 'var(--bib)', 'var(--muted)'][i], dashed: i > 0,
      }))} />
      <p className="note" style={{ marginTop: '.8rem' }}>Rules: {bt.rules} Leaving out chips and auto-subs makes every strategy score less than a real team would, so compare the strategies with each other rather than with real FPL scores.</p>
    </Card>
  )
}
