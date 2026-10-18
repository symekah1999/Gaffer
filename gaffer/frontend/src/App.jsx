import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { supabase } from './supabase.js'
import { useHashRoute } from './hooks.js'
import Shell from './components/Shell.jsx'
import { Card, Loading } from './components/ui.jsx'
import Home from './pages/Home.jsx'
import MyTeam from './pages/MyTeam.jsx'
import Results from './pages/Results.jsx'
import Insights from './pages/Insights.jsx'
import Players from './pages/Players.jsx'
import Fixtures from './pages/Fixtures.jsx'
import Builder from './pages/Builder.jsx'
import ModelInfo from './pages/ModelInfo.jsx'

const DEFAULTS = { team_id: '', free_transfers: 1, horizon: 5 }

export default function App() {
  const route = useHashRoute('home')
  const [status, setStatus] = useState(null)
  const [session, setSession] = useState(null)
  const [settings, setSettings] = useState(() => ({ ...DEFAULTS, ...JSON.parse(localStorage.getItem('gaffer_settings') || '{}') }))

  useEffect(() => {
    api('/status').then(setStatus).catch(() => setStatus({ state: 'error', message: 'Cannot reach the Gaffer API.' }))
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!session) return
    api('/me').then((m) => m.team_id && setSettings((s) => {
      const next = { ...s, team_id: String(m.team_id), free_transfers: m.free_transfers, horizon: m.horizon }
      localStorage.setItem('gaffer_settings', JSON.stringify(next))
      return next
    })).catch(() => {})
  }, [session])

  const save = useCallback((patch) => {
    setSettings((s) => {
      const next = { ...s, ...patch }
      localStorage.setItem('gaffer_settings', JSON.stringify(next))
      if (session && next.team_id) {
        api('/me', { team_id: Number(next.team_id), free_transfers: Number(next.free_transfers), horizon: Number(next.horizon) }, 'PUT').catch(() => {})
      }
      return next
    })
  }, [session])

  const ctx = { status, session, settings, save }
  let page
  if (!status) page = <Loading rows={3} />
  else if (status.state !== 'ready') page = (
    <Card><div className="empty"><h2>{status.state === 'empty' ? 'No projections yet' : 'Something went wrong'}</h2><p>{status.message}</p></div></Card>
  )
  else page = {
    home: <Home {...ctx} />, team: <MyTeam {...ctx} />, results: <Results {...ctx} />, insights: <Insights {...ctx} />,
    players: <Players />, fixtures: <Fixtures />, build: <Builder {...ctx} />, model: <ModelInfo />,
  }[route] || <Home {...ctx} />

  return (
    <Shell route={route} status={status} session={session}>
      {status?.source === 'mock' && <div className="note" style={{ marginBottom: '1rem' }}>Demo data: a simulated league for testing. Remove the FPL_MOCK variable in GitHub to use real FPL data.</div>}
      {page}
    </Shell>
  )
}
