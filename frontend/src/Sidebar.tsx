import { useState } from 'react'
import type { HubScore } from './api'
import { AGENT_NAME } from './brand'
import { MethodPanel } from './MethodPanel'
import { RankingPanel } from './RankingPanel'

type Tab = 'ranking' | 'method'

/** Navy sidebar: brand, a two-tab switch (ranking / how we rank) and "New conversation". */
export function Sidebar(props: {
  open: boolean
  onClose: () => void
  onAskAbout: (hub: HubScore) => void
  onNewConversation: () => void
  busy: boolean
  canReset: boolean
}) {
  const [tab, setTab] = useState<Tab>('ranking')
  return (
    <nav className={`sidebar ${props.open ? 'open' : ''}`} aria-label="Hub ranking and method">
      <div className="side-brand">
        <span className="logo" aria-hidden>🛰️</span>
        <div>
          <div className="brand-name">{AGENT_NAME}</div>
          <div className="brand-tag">Weather risk agent</div>
        </div>
        <button className="side-close" onClick={props.onClose} aria-label="Close menu">✕</button>
      </div>

      <button className="new-chat" onClick={props.onNewConversation} disabled={props.busy || !props.canReset}>
        + New conversation
      </button>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'ranking'} className={tab === 'ranking' ? 'active' : ''}
                onClick={() => setTab('ranking')}>Most exposed</button>
        <button role="tab" aria-selected={tab === 'method'} className={tab === 'method' ? 'active' : ''}
                onClick={() => setTab('method')}>How we rank</button>
      </div>

      <div className="side-scroll">
        {tab === 'ranking'
          ? <RankingPanel onAskAbout={props.onAskAbout} disabled={props.busy} />
          : <MethodPanel />}
      </div>
    </nav>
  )
}
