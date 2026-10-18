import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: !!path })
  const load = useCallback(() => {
    if (!path) return setState({ data: null, error: null, loading: false })
    setState((s) => ({ ...s, loading: true, error: null }))
    api(path).then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
  }, [path])
  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}

export function useHashRoute(fallback) {
  const read = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] || fallback)
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export function useNow(ms = 30000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t) }, [ms])
  return now
}

export function useInstall() {
  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
  const [evt, setEvt] = useState(null)
  const [installed, setInstalled] = useState(standalone)
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setEvt(e) }
    const onInstalled = () => { setInstalled(true); setEvt(null) }
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => { window.removeEventListener('beforeinstallprompt', onPrompt); window.removeEventListener('appinstalled', onInstalled) }
  }, [])
  const ua = navigator.userAgent
  return {
    installed, canPrompt: !!evt,
    platform: /iphone|ipad|ipod/i.test(ua) ? 'ios' : /android/i.test(ua) ? 'android' : 'desktop',
    prompt: async () => { if (!evt) return false; evt.prompt(); const r = await evt.userChoice; setEvt(null); return r.outcome === 'accepted' },
  }
}
