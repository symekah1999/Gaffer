import { supabase } from './supabase.js'

export async function api(path, body, method) {
  const headers = {}
  if (supabase) {
    const { data } = await supabase.auth.getSession()
    if (data.session) headers.Authorization = 'Bearer ' + data.session.access_token
  }
  const opts = { method: method || (body ? 'POST' : 'GET'), headers }
  if (body) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body) }
  const r = await fetch('/api' + path, opts)
  if (!r.ok) {
    const e = await r.json().catch(() => ({}))
    const d = e.detail
    const err = new Error(typeof d === 'string' ? d : Array.isArray(d) ? 'Please check the values you entered.' : d?.message || `Request failed (${r.status})`)
    err.status = r.status
    throw err
  }
  return r.json()
}
