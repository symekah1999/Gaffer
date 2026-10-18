import { useApi } from '../hooks.js'
import { Card, PageHead, Loading, ErrorBox, Stat } from '../components/ui.jsx'
import { LineChart } from '../components/Charts.jsx'
import SeasonSim from '../components/SeasonSim.jsx'
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
      <SeasonSim bt={m.backtest} />
      {h.length > 0 && (
        <>
          <Card title="Season track record" sub="Every finished gameweek, scored against what actually happened">
            <div className="stats" style={{ marginBottom: '1rem' }}>
              <Stat value={f1(avg('top10_avg'))} label="Gaffer's top 10 picks, average points per week" />
              <Stat value={f1(avg('price_top10_avg'))} label="10 most expensive players (rival)" />
              <Stat value={f1(avg('form_top10_avg'))} label="10 in-form players (rival)" />
              <Stat value={f1(avg('field_avg'))} label="average player who played" />
            </div>
            <LineChart labels={h.map((r) => `GW${r.gw}`)} series={[
              { name: "Gaffer's top 10", values: h.map((r) => r.top10_avg), color: 'var(--turf)' },
              { name: 'Top 10 by price', values: h.map((r) => r.price_top10_avg ?? null), color: 'var(--bib)', dashed: true },
              { name: 'Top 10 by form', values: h.map((r) => r.form_top10_avg ?? null), color: '#7b8fd6', dashed: true },
              { name: 'Average player', values: h.map((r) => r.field_avg), color: 'var(--muted)', dashed: true },
            ]} />
            <p className="muted" style={{ marginTop: '.6rem', marginBottom: 0 }}>The real test is beating the rivals, not just the average player: anyone picking expensive or in-form players beats the average.</p>
          </Card>
          <Card title="By gameweek">
            <div className="tablewrap">
              <table>
                <thead><tr><th>Gameweek</th><th>Predictions</th><th className="num">Avg error</th><th className="num">Correlation</th><th className="num">Gaffer top 10</th><th className="num">Price top 10</th><th className="num">Form top 10</th><th className="num">Field avg</th></tr></thead>
                <tbody>{[...h].reverse().map((r) => (
                  <tr key={r.gw}><td><b>GW{r.gw}</b></td><td>{r.kind === 'backtest' ? <span className="tag plain">Rebuilt</span> : <span className="tag">Pre-deadline</span>}</td>
                    <td className="num">{f2(r.mae)}</td><td className="num">{f2(r.corr)}</td><td className="num"><b>{f1(r.top10_avg)}</b></td><td className="num">{f1(r.price_top10_avg)}</td><td className="num">{f1(r.form_top10_avg)}</td><td className="num">{f1(r.field_avg)}</td></tr>
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
            <li><b>Machine learning:</b> LightGBM models trained on four past seasons plus this one (over 100,000 player-matches), predicting points and the chance of a 10+ haul. They are weighted only as far as they beat a simple form guess on unseen data.</li>
            <li><b>Transfer planner:</b> plans several gameweeks at once, banking free transfers (up to 5) and only taking hits that clearly pay back.</li>
            <li><b>Optimiser:</b> an integer program picks squad, XI, captain and transfers under budget, club and formation rules.</li>
          </ol>
        </Card>
        <Card title="Machine-learning check" sub="Tested on matches the model had not seen">
          {ml.season_test && (
            <div style={{ marginBottom: '1rem' }}>
              <h3>Full {ml.season_test.season} season test</h3>
              <p className="muted">Trained only on earlier seasons, then asked to predict all {ml.season_test.n.toLocaleString()} player-matches of {ml.season_test.season}.</p>
              <div className="stats">
                <Stat value={`${(ml.season_test.skill * 100).toFixed(1)}%`} label="lower error than the form guess" />
                <Stat value={f2(ml.season_test.corr)} label="correlation with actual points" />
                {ml.season_test.haul_auc != null && <Stat value={`${Math.round(ml.season_test.haul_auc * 100)}%`} label="of the time it ranks a real haul above a non-haul" />}
              </div>
            </div>
          )}
          {ml.enabled ? (
            <>
              <div className="stats">
                <Stat value={f2(ml.mae)} label={`ML average error (form baseline ${f2(ml.baseline_mae)})`} />
                <Stat value={`${(ml.skill * 100).toFixed(1)}%`} label="improvement over form" />
                <Stat value={`${Math.round(ml.weight * 100)}%`} label="weight in final projections" />
              </div>
              {ml.validated_on?.length > 0 && <p className="muted" style={{ marginTop: '.8rem' }}>This season: validated on GW{ml.validated_on.join(', GW')} ({ml.n_val} player-matches).</p>}
            </>
          ) : <p className="muted">Switched off for now: {ml.reason}. Projections use the statistical model alone.</p>}
          <p className="note" style={{ marginTop: '.8rem' }}>Single-match FPL points are mostly luck, so even a strong model explains only a modest share of them. Judge it over many weeks: the useful test is whether its top picks consistently outscore the average player.</p>
        </Card>
      </div>
    </div>
  )
}
