import { useEffect, useRef, useState } from 'react'
import { f1 } from '../util.js'

export function LineChart({ labels, series, height = 230, yFormat = f1 }) {
  const ref = useRef(null)
  const [W, setW] = useState(640)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  const H = W < 480 ? Math.round(height * 0.85) : height, L = 34, R = 10, T = 12, B = 26
  const all = series.flatMap((s) => s.values).filter((v) => v != null)
  if (!all.length) return <div ref={ref} />
  let lo = Math.min(0, ...all), hi = Math.max(...all)
  if (hi === lo) hi = lo + 1
  const pad = (hi - lo) * 0.08; hi += pad
  const x = (i) => L + (labels.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (labels.length - 1))
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4)
  const step = Math.ceil(labels.length / Math.max(4, Math.floor(W / 56)))
  return (
    <div ref={ref}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={series.map((s) => s.name).join(' vs ')}>
        <g className="grid">
          {ticks.map((t, i) => <g key={i}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} /><text x={L - 6} y={y(t) + 4} textAnchor="end">{Math.round(t)}</text></g>)}
        </g>
        {labels.map((l, i) => i % step === 0 && <text key={i} x={x(i)} y={H - 6} textAnchor="middle">{l}</text>)}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean)
          return (
            <g key={s.name}>
              <polyline fill="none" stroke={s.color} strokeWidth="2.5" strokeDasharray={s.dashed ? '6 5' : undefined} strokeLinejoin="round" points={pts.map((p) => p.join(',')).join(' ')} />
              {s.values.map((v, i) => v != null && (
                <circle key={i} cx={x(i)} cy={y(v)} r="3.6" fill={s.dashed ? 'var(--surface)' : s.color} stroke={s.color} strokeWidth="2">
                  <title>{`${labels[i]}: ${s.name} ${yFormat(v)}`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color, opacity: s.dashed ? 0.7 : 1 }} />{s.name}</span>)}</div>
    </div>
  )
}
