import { useEffect } from 'react'
import { X } from 'lucide-react'
import { f1 } from '../util.js'

export function Card({ title, icon: Icon, sub, action, children, className = '' }) {
  return (
    <section className={'card ' + className}>
      {(title || action) && (
        <div className="card-head">
          <div>
            {title && <h2>{Icon && <Icon size={18} aria-hidden="true" />}{title}</h2>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function PageHead({ title, intro, actions }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{intro && <p>{intro}</p>}</div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  )
}

export function Stat({ value, label, tone }) {
  return <div className="stat"><b className={tone || ''}>{value}</b><span>{label}</span></div>
}

export function PlayerRow({ p, value, sub, max }) {
  return (
    <li className="prow">
      <span className="badge" aria-hidden="true">{p.team}</span>
      <div style={{ minWidth: 0 }}>
        <div className="pname">{p.name}</div>
        <div className="pmeta">{p.pos_name} · £{f1(p.price)}m · {f1(p.selected)}% owned · {p.fixture}</div>
        {max ? <div className="bar"><div style={{ width: `${Math.max(4, Math.min(100, (Number(value) / max) * 100))}%` }} /></div> : null}
      </div>
      <div className="pval">{typeof value === 'number' ? f1(value) : value}{sub && <small>{sub}</small>}</div>
    </li>
  )
}

export function Loading({ rows = 2 }) {
  return <div className="stack" aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}</div>
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="card empty">
      <h2>Couldn't load this</h2>
      <p>{error?.message || 'Something went wrong.'}</p>
      {onRetry && <button className="btn secondary" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={20} /></button></div>
        {children}
      </div>
    </div>
  )
}

export function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  )
}
