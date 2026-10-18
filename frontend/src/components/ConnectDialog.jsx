import { useState } from 'react'
import { api } from '../api.js'
import { Modal } from './ui.jsx'

export default function ConnectDialog({ current, onSave, onClose }) {
  const [value, setValue] = useState(current || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [found, setFound] = useState(null)

  const parse = (v) => (v.match(/entry\/(\d+)/) || v.match(/^\s*(\d{3,9})\s*$/) || [])[1]

  async function submit(e) {
    e.preventDefault(); setErr(''); setFound(null)
    const id = parse(value)
    if (!id) return setErr('Paste your team link or just the number (for example 5133387).')
    setBusy(true)
    try { setFound(await api(`/team?team_id=${id}`)) } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <Modal title="Connect your FPL team" onClose={onClose}>
      <p className="muted">Gaffer only needs your public team ID, never your FPL password. Paste your team link or the number from it. You do this once, and it is remembered on this device (and on all your devices if you sign in).</p>
      <form onSubmit={submit} className="stack" style={{ gap: '.7rem' }}>
        <label className="field">Team link or ID
          <input className="input" autoFocus value={value} onChange={(e) => { setValue(e.target.value); setFound(null) }} placeholder="fantasy.premierleague.com/entry/1234567/event/7" />
          <small>Open Points on the FPL site and copy the address from your browser.</small>
        </label>
        {err && <p className="error" role="alert">{err}</p>}
        {found ? (
          <>
            <div className="note"><b>{found.name}</b><br />{found.manager}{found.points ? ` · ${found.points} points` : ''}</div>
            <button type="button" className="btn" onClick={() => onSave(String(found.team_id))}>Yes, connect this team</button>
          </>
        ) : <button className="btn" disabled={busy}>{busy ? 'Checking…' : 'Find my team'}</button>}
      </form>
    </Modal>
  )
}
