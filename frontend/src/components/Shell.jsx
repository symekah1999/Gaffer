import { useEffect, useState } from 'react'
import { Link2, Home, Shirt, Trophy, Lightbulb, Users, CalendarDays, Wrench, Gauge, Download, Menu, X, LogIn, LogOut } from 'lucide-react'
import { supabase } from '../supabase.js'
import { useInstall } from '../hooks.js'
import { ago } from '../util.js'
import AccountDialog from './AccountDialog.jsx'
import InstallDialog from './InstallDialog.jsx'

export const PAGES = [
  ['home', 'Dashboard', Home],
  ['team', 'My team', Shirt],
  ['results', 'Weekly results', Trophy],
  ['insights', 'Insights', Lightbulb],
  ['sep'],
  ['players', 'Players', Users],
  ['fixtures', 'Fixtures', CalendarDays],
  ['build', 'Squad builder', Wrench],
  ['model', 'Model & accuracy', Gauge],
]

export default function Shell({ route, status, session, team, teamId, openConnect, children }) {
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(null)
  const install = useInstall()
  useEffect(() => setOpen(false), [route])
  const current = PAGES.find((p) => p[0] === route)

  return (
    <div className="shell">
      <header className="appbar">
        <button className="icon-btn" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open}><Menu size={24} /></button>
        <span className="title">{current?.[1] || 'Gaffer'}</span>
        {status?.next_gw && <span className="gw">GW{status.next_gw}</span>}
      </header>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <aside className={'side' + (open ? ' open' : '')} aria-label="Main menu">
        <div className="brand">
          <img src="/icon-192.png" alt="" />
          <div><b>Gaffer</b><span>FPL planner</span></div>
          {open && <button className="icon-btn" style={{ marginLeft: 'auto' }} onClick={() => setOpen(false)} aria-label="Close menu"><X size={22} /></button>}
        </div>
        <button className="team-chip" onClick={openConnect}>
          <Link2 size={17} aria-hidden="true" />
          <span>
            {teamId ? <><b>{team?.name || `Team ${teamId}`}</b><small>{team?.manager ? `${team.manager} · ` : ''}Change team</small></> : <><b>Connect your FPL team</b><small>One time, takes 10 seconds</small></>}
          </span>
        </button>
        <nav className="nav">
          {PAGES.map(([k, label, Icon], i) => k === 'sep' ? <div key={i} className="nav-sep" /> : (
            <a key={k} href={`#/${k}`} aria-current={route === k ? 'page' : undefined}><Icon size={19} aria-hidden="true" />{label}</a>
          ))}
        </nav>
        <div className="side-foot">
          {status?.updated_at && <div className="side-data">Data updated {ago(status.updated_at)}</div>}
          {!install.installed && (
            <button className="side-btn" onClick={async () => { if (!(await install.prompt())) setDialog('install') }}>
              <Download size={18} aria-hidden="true" /> Install app
            </button>
          )}
          {supabase && (session ? (
            <>
              <div className="side-user">{session.user.email}</div>
              <button className="side-btn" onClick={() => supabase.auth.signOut()}><LogOut size={18} aria-hidden="true" /> Sign out</button>
            </>
          ) : (
            <button className="side-btn" onClick={() => setDialog('account')}><LogIn size={18} aria-hidden="true" /> Sign in</button>
          ))}
        </div>
      </aside>

      <main className="content" id="main">{children}</main>
      {dialog === 'account' && <AccountDialog onClose={() => setDialog(null)} />}
      {dialog === 'install' && <InstallDialog platform={install.platform} onClose={() => setDialog(null)} />}
    </div>
  )
}
