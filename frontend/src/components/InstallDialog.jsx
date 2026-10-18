import { Modal } from './ui.jsx'

const STEPS = {
  ios: ['Open this site in Safari.', 'Tap the Share button.', 'Choose Add to Home Screen, then Add.'],
  android: ['Open this site in Chrome.', 'Tap the ⋮ menu.', 'Choose Install app (or Add to Home screen).'],
  desktop: ['Open this site in Chrome or Edge.', 'Click the install icon at the right of the address bar (or the ⋮ menu > Install Gaffer).', 'Gaffer opens in its own window and appears in your apps.'],
}

export default function InstallDialog({ platform, onClose }) {
  return (
    <Modal title="Install Gaffer" onClose={onClose}>
      <p className="muted">Install it like an app: its own icon, full screen, and quick to open.</p>
      <ol className="steps">{STEPS[platform].map((s) => <li key={s}>{s}</li>)}</ol>
      <details>
        <summary className="muted">Other devices</summary>
        {Object.entries(STEPS).filter(([k]) => k !== platform).map(([k, steps]) => (
          <div key={k} style={{ marginTop: '.6rem' }}>
            <b>{k === 'ios' ? 'iPhone / iPad' : k === 'android' ? 'Android' : 'Windows / Mac'}</b>
            <ol className="steps">{steps.map((s) => <li key={s}>{s}</li>)}</ol>
          </div>
        ))}
      </details>
      <button className="btn" onClick={onClose}>Got it</button>
    </Modal>
  )
}
