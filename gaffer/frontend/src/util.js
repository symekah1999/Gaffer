export const f1 = (n) => (n == null || isNaN(n) ? '–' : (Math.round(n * 10) / 10).toFixed(1))
export const f2 = (n) => (n == null || isNaN(n) ? '–' : Number(n).toFixed(2))
export const int = (n) => (n == null ? '–' : Math.round(n).toLocaleString())
export const sum = (a) => a.reduce((x, y) => x + (Number(y) || 0), 0)
export const signed = (n) => (n > 0 ? '+' : '') + f1(n)

export function ago(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000))
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`
}

export function countdown(iso, now = Date.now()) {
  const ms = new Date(iso) - now
  if (ms <= 0) return 'Deadline passed'
  const d = Math.floor(ms / 864e5), h = Math.floor((ms % 864e5) / 36e5), m = Math.floor((ms % 36e5) / 6e4)
  return d ? `${d}d ${h}h ${m}m` : h ? `${h}h ${m}m` : `${m}m`
}

export const localTime = (iso) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function downloadCSV(filename, rows, cols) {
  const esc = (v) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  const text = [cols.map((c) => esc(c[0])).join(','), ...rows.map((r) => cols.map((c) => esc(c[1](r))).join(','))].join('\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
}
