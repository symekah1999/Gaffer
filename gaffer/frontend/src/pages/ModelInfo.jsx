import { useApi } from '../hooks.js'
import { Card, PageHead, Loading, ErrorBox, Stat } from '../components/ui.jsx'
import { LineChart } from '../components/Charts.jsx'
import { f1, f2, ago } from '../util.js'

export default function ModelInfo() {
  const { data: m, error, loading, reload } = useApi('/model')
  if (loading) return <Loading rows={3} />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const ml = m.ml || {}, h = m.history || []
  const avg = (k) => (h.length ? h.reduce((a, r) => a + (r[k] || 0), 0) / h.length : null)
  return (
    <div className="stack">
      <PageHead title="Model and accuracy" intro={`Projections refresh every 4 hours. Last update ${ago(m.updated_at)}.`} />
      {h.length > 0 && (
        <>
          <Card title="Season track record" sub="Every finished gameweek, scored against what actually happened">
            <div className="stats" style={{ marginBottom: '1rem' }}>
              <Stat value={f1(avg('top10_avg'))} label="average points of Gaffer's top 10 picks per week" />
              <Stat value={f1(avg('field_avg'))} label="average points of all players who played" />
              <Stat value={f2(avg('mae'))} label="average error per player (points)" />
              <Stat value={f2(avg('corr'))} label="correlation between predicted and actual" />
            </div>
            <LineChart labels={h.map((r) => `GW${r.gw}`)} series={[
              { name: "Gaffer's top 10", values: h.map((r) => r.top10_avg), color: 'var(--turf)' },
              { name: 'Average player', values: h.map((r) => r.field_avg), color: 'var(--muted)', dashed: true },
            ]} />
          </Card>
          <Card title="By gameweek">
            <div className="tablewrap">
              <table>
                <thead><tr><th>Gameweek</th><th>Predictions</th><th className="num">Players</th><th className="num">Avg error</th><th className="num">Correlation</th><th className="num">Top 10 avg</th><th className="num">Field avg</th></tr></thead>
                <tbody>{[...h].reverse().map((r) => (
                  <tr key={r.gw}><td><b>GW{r.gw}</b></td><td>{r.kind === 'backtest' ? <span className="tag plain">Rebuilt</span> : <span className="tag">Pre-deadline</span>}</td>
                    <td className="num">{r.n}</td><td className="num">{f2(r.mae)}</td><td className="num">{f2(r.corr)}</td><td className="num">{f1(r.top10_avg)}</td><td className="num">{f1(r.field_avg)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      <div className="grid two">
        <Card title="How the projections work">
          <ol className="steps">
            <li><b>Team strength:</b> attack and defence ratings for every club, home and away, from this season's results, blended with FPL's own strength numbers early on.</li>
            <li><b>Expected scoreline</b> for every fixture, which drives goals, assists, clean sheets and bonus.</li>
            <li><b>Player rates</b> per 90 minutes, blending expected and actual output, weighting recent games, and pulling small samples towards last season and the position average.</li>
            <li><b>Minutes and availability</b> from recent starts and FPL injury and suspension news.</li>
            <li><b>Every FPL scoring rule</b>, including clean sheets, goals conceded, saves, defensive actions and double gameweeks.</li>
            <li><b>Machine-learning correction:</b> a LightGBM model trained on this season's matches, weighted only as much as it beats a simple form baseline.</li>
            <li><b>Optimiser:</b> an integer program picks squad, XI, captain and transfers under budget, club and formation rules.</li>
          </ol>
        </Card>
        <Card title="Machine-learning check" sub="Tested on recent gameweeks the model had not seen">
          {ml.enabled ? (
            <>
              <div className="stats">
                <Stat value={f2(ml.mae)} label={`ML average error (form baseline ${f2(ml.baseline_mae)})`} />
                <Stat value={`${(ml.skill * 100).toFixed(1)}%`} label="improvement over form" />
                <Stat value={`${Math.round(ml.weight * 100)}%`} label="weight in final projections" />
              </div>
              <p className="muted" style={{ marginTop: '.8rem' }}>Validated on GW{ml.validated_on.join(', GW')} ({ml.n_val} player-matches).</p>
            </>
          ) : <p className="muted">Switched off for now: {ml.reason}. Projections use the statistical model alone.</p>}
          <p className="note" style={{ marginTop: '.8rem' }}>Single-match FPL points are mostly luck, so even a strong model explains only a modest share of them. Judge it over many weeks: the useful test is whether its top picks consistently outscore the average player.</p>
        </Card>
      </div>
    </div>
  )
}
