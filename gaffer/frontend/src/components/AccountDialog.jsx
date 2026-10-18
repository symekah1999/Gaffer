import { useState } from 'react'
import { supabase } from '../supabase.js'
import { Modal } from './ui.jsx'

export default function AccountDialog({ onClose }) {
  const [mode, setMode] = useState('in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault(); setBusy(true); setMsg('')
    const { data, error } = mode === 'in'
      ? await supabase.auth.signInWithPassword({ email, password })
      : await supabase.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } })
    setBusy(false)
    if (error) return setMsg(error.message)
    if (mode === 'up' && !data.session) return setMsg('Account created. Confirm it from the email we sent, then sign in.')
    onClose()
  }

  return (
    <Modal title={mode === 'in' ? 'Sign in' : 'Create an account'} onClose={onClose}>
      <p className="muted">Signing in saves your team ID and settings across devices, and turns on weekly results for your team.</p>
      <form onSubmit={submit} className="stack" style={{ gap: '.7rem' }}>
        <label className="field">Email<input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field">Password<input className="input" type="password" required minLength={6} autoComplete={mode === 'in' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {msg && <p className="error" role="alert">{msg}</p>}
        <button className="btn" disabled={busy}>{busy ? 'Please wait…' : mode === 'in' ? 'Sign in' : 'Create account'}</button>
      </form>
      <button className="linkbtn" onClick={() => { setMode(mode === 'in' ? 'up' : 'in'); setMsg('') }}>
        {mode === 'in' ? 'New here? Create an account' : 'Already have an account? Sign in'}
      </button>
    </Modal>
  )
}
