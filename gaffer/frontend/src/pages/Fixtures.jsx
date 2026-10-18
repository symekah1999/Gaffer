import { useMemo, useState } from 'react'
import { useApi } from '../hooks.js'
import { Card, PageHead, Loading, ErrorBox, Seg } from '../components/ui.jsx'

export default function Fixtures() {
  const { data, error, loading, reload } = useApi('/fixtures')
  const [mode, setMode] = useState('att')
  const range = useMemo(() => {
    if (!data) return [0, 1]
    const v = data.teams.flatMap((t) => Object.values(t.fixtures).flat().map((f) => (mode === 'att' ? f.xgf : f.xga)))
    return [Math.min(...v), Math.max(...v)]
  }, [data, mode])
  if (loading) return <Loading rows={3} />
  if (error) return <ErrorBox error={error} onRetry={reload} />

  const ease = (f) => { let t = ((mode === 'att' ? f.xgf : f.xga) - range[0]) / (range[1] - range[0] || 1); return mode === 'def' ? 1 - t : t }
  const tint = (f) => `hsl(${Math.round(ease(f) * 125)} 52% 78%)`
  const run = (t) => Object.values(t.fixtures).flat().reduce((n, f) => n + ease(f), 0)
  const sorted = [...data.teams].sort((a, b) => run(b) - run(a))
  return (
    <div className="stack">
      <PageHead title="Fixtures" intro="Difficulty from the model's expected goals for each match, not FPL's 1–5 ratings. Greener is easier. Teams are ordered by their whole run." />
      <Card action={null}>
        <div style={{ marginBottom: '1rem' }}>
          <Seg label="Show ease for" value={mode} onChange={setMode} options={[['att', 'Attackers'], ['def', 'Defenders & keepers']]} />
        </div>
        <div className="tablewrap">
          <table className="fix">
            <thead><tr><th className="sticky">Team</th>{data.gws.map((g) => <th key={g} style={{ textAlign: 'center' }}>GW{g}</th>)}</tr></thead>
            <tbody>
              {sorted.map((t) => (
                <tr key={t.team}>
                  <td className="sticky"><b>{t.short}</b></td>
                  {data.gws.map((g) => {
                    const fx = t.fixtures[g] || t.fixtures[String(g)] || []
                    return (
                      <td key={g}>
                        {fx.length === 0 ? <div className="fx" style={{ background: 'var(--surface-2)', color: 'var(--muted)' }}>Blank</div>
                          : fx.map((f, i) => <div key={i} className="fx" style={{ background: tint(f) }} title={`Expected goals ${f.xgf.toFixed(2)}, conceded ${f.xga.toFixed(2)}`}>{f.opp} <small>{f.home ? 'H' : 'A'}</small></div>)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
