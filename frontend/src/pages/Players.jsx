import { Fragment, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { useApi } from '../hooks.js'
import { Card, PageHead, Loading, ErrorBox, Seg } from '../components/ui.jsx'
import { downloadCSV, f1 } from '../util.js'

const LABELS = { appearance: 'Appearance', goals: 'Goals', assists: 'Assists', clean_sheet: 'Clean sheet', conceded: 'Goals conceded', saves: 'Saves', bonus: 'Bonus', cards: 'Cards', defensive: 'Defensive actions' }

export default function Players() {
  const { data, error, loading, reload } = useApi('/players')
  const [q, setQ] = useState('')
  const [pos, setPos] = useState(0)
  const [maxPrice, setMaxPrice] = useState(15)
  const [sort, setSort] = useState('xp_total')
  const [open, setOpen] = useState(null)

  const rows = useMemo(() => !data ? [] : data.players
    .filter((p) => (!pos || p.pos === pos) && p.price <= maxPrice && (p.name + ' ' + p.team_short).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (b[sort] ?? 0) - (a[sort] ?? 0)), [data, q, pos, maxPrice, sort])
  if (loading) return <Loading rows={3} />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const shown = rows.slice(0, 150)
  const maxXp = Math.max(...shown.flatMap((r) => data.gws.map((g) => r[`xp_${g}`] || 0)), 1)
  const th = (key, label, cls = 'num') => <th className={cls}><button className="sort" aria-pressed={sort === key} onClick={() => setSort(key)}>{label}</button></th>
  const exportCSV = () => downloadCSV('gaffer-projections.csv', rows, [
    ['Player', (p) => p.name], ['Team', (p) => p.team_short], ['Position', (p) => p.pos_name], ['Price', (p) => p.price],
    ['Chance of playing', (p) => p.p_play], ['Owned %', (p) => p.selected], ['Haul chance next GW', (p) => p.haul_next],
    ...data.gws.map((g) => [`GW${g} xP`, (p) => p[`xp_${g}`]]), ['Total xP', (p) => p.xp_total], ['xP per £m', (p) => p.value_per_m],
  ])

  return (
    <div className="stack">
      <PageHead title="Players" intro="Expected points for every player over the next 8 gameweeks, and the chance of a 10+ point haul next gameweek. Tap a player to see what drives the number."
        actions={<button className="btn secondary" onClick={exportCSV}><Download size={16} /> CSV</button>} />
      <Card>
        <div className="form" style={{ marginBottom: '1rem' }}>
          <label className="field">Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or club" /></label>
          <div className="field">Position<Seg label="Position" value={pos} onChange={setPos} options={[[0, 'All'], [1, 'GK'], [2, 'DEF'], [3, 'MID'], [4, 'FWD']]} /></div>
          <label className="field">Max price: £{maxPrice}m<input type="range" min="4" max="15" step="0.5" value={maxPrice} onChange={(e) => setMaxPrice(Number(e.target.value))} /></label>
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr>
              <th className="sticky">Player</th>{th('price', '£m')}{th('p_play', 'Plays')}{th('selected', 'Owned')}{th('haul_next', 'Haul %')}
              {data.gws.map((g) => <Fragment key={g}>{th(`xp_${g}`, `GW${g}`, 'heat')}</Fragment>)}
              {th('xp_total', 'Total')}{th('value_per_m', 'Per £m')}
            </tr></thead>
            <tbody>
              {shown.map((p) => (
                <Fragment key={p.id}>
                  <tr className="clickable" onClick={() => setOpen(open === p.id ? null : p.id)}>
                    <td className="sticky"><b>{p.name}</b> <small>{p.team_short} · {p.pos_name}</small>{p.news && <div className="error" style={{ fontSize: '.74rem', whiteSpace: 'normal', maxWidth: '16rem' }}>{p.news}</div>}</td>
                    <td className="num">{f1(p.price)}</td>
                    <td className="num">{Math.round(p.p_play * 100)}%</td>
                    <td className="num">{f1(p.selected)}%</td>
                    <td className="num">{p.haul_next != null ? `${Math.round(p.haul_next * 100)}%` : '–'}</td>
                    {data.gws.map((g) => (
                      <td key={g} className="heat" style={{ background: `rgba(var(--heat), ${Math.min(0.55, ((p[`xp_${g}`] || 0) / maxXp) * 0.55)})` }}>
                        {f1(p[`xp_${g}`])}<small>{p.fixtures?.[g]}</small>
                      </td>
                    ))}
                    <td className="num"><b>{f1(p.xp_total)}</b></td>
                    <td className="num">{f1(p.value_per_m)}</td>
                  </tr>
                  {open === p.id && (
                    <tr className="detail"><td colSpan={7 + data.gws.length}>
                      <div className="chips">
                        <span>GW{data.gws[0]} breakdown:</span>
                        {Object.entries(p.bd || {}).filter(([, v]) => Math.abs(v) >= 0.01).map(([k, v]) => <span key={k} className="chip">{LABELS[k]} <b>{v > 0 ? '+' : ''}{f1(v)}</b></span>)}
                        <span className="chip">Expected minutes <b>{p.e_min}</b></span>
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ marginTop: '.8rem', marginBottom: 0 }}>Showing {shown.length} of {rows.length}. The CSV download includes all of them.</p>
      </Card>
    </div>
  )
}
