import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { AnswerCard } from './AnswerCard'
import { sendChat, type ChatResponse, type HubScore } from './api'
import { AGENT_NAME } from './brand'
import { MethodPanel } from './MethodPanel'
import { RankingPanel } from './RankingPanel'
import './App.css'

type Turn =
  | { role: 'user'; text: string }
  | { role: 'agent'; reply: ChatResponse }
  | { role: 'error'; text: string; retry: string }

type Overlay = 'method' | 'ranking' | null // side panels shown as overlays on narrow screens

const EXAMPLES = [
  { icon: '❄️', tag: 'Rank', q: 'Which hubs in the Midwest are most exposed to winter disruption?' },
  { icon: '🌀', tag: 'Compare', q: 'Compare Miami and Houston in terms of hurricane and flood exposure.' },
  { icon: '📅', tag: 'Weather history', q: 'What percentage of days in Denver last year had snowfall?' },
  { icon: '🔎', tag: 'Explain', q: "Why is the Dallas hub's weather disruption risk high?" },
]

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [overlay, setOverlay] = useState<Overlay>(null)
  const endRef = useRef<HTMLDivElement>(null)

  // Scroll to the newest message when the list changes. Braces matter: an effect may only return a
  // cleanup function, and scrollIntoView returns a Promise in current browsers.
  useEffect(() => {
    if (turns.length > 0 || pending) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, pending])

  async function ask(text: string) {
    const message = text.trim()
    if (!message || pending) return
    setTurns((t) => [...t.filter((x) => x.role !== 'error'), { role: 'user', text: message }])
    setDraft('')
    setPending(true)
    setOverlay(null)
    try {
      const reply = await sendChat(message, conversationId)
      setConversationId(reply.conversation_id)
      setTurns((t) => [...t, { role: 'agent', reply }])
    } catch (err) {
      // Drop the unanswered question so Retry re-sends it cleanly.
      setTurns((t) => [...t.slice(0, -1), { role: 'error', text: (err as Error).message, retry: message }])
    } finally {
      setPending(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    ask(draft)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { // Enter sends, Shift+Enter adds a line
      e.preventDefault()
      ask(draft)
    }
  }

  function askAboutHub(hub: HubScore) {
    ask(`What drives the ${hub.name} hub's weather risk score?`)
  }

  function toggle(panel: Exclude<Overlay, null>) {
    setOverlay((o) => (o === panel ? null : panel))
  }

  function newConversation() {
    setTurns([])
    setConversationId(null)
  }

  return (
    <div className="layout">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>🛰️</span>
          <div>
            <h1>{AGENT_NAME} <span className="brand-light">Weather Risk Agent</span></h1>
            <p>Know which hubs to protect first</p>
          </div>
        </div>
        <div className="top-actions">
          <button className="ghost toggle-method" onClick={() => toggle('method')}>
            {overlay === 'method' ? 'Close' : 'How we rank'}
          </button>
          <button className="ghost toggle-ranking" onClick={() => toggle('ranking')}>
            {overlay === 'ranking' ? 'Close' : 'Ranking'}
          </button>
          <button className="ghost" onClick={newConversation} disabled={pending || turns.length === 0}>
            New<span className="wide-only"> conversation</span>
          </button>
        </div>
      </header>

      <div className={`body overlay-${overlay ?? 'none'}`}>
        <MethodPanel />

        <section className="chat-column">
          <main className="chat" aria-live="polite">
            <div className="msg agent intro">
              <div className="avatar" aria-hidden>🛰️</div>
              <div>
                <p className="intro-hello">Hi, I'm {AGENT_NAME}, your weather risk agent.</p>
                <p>
                  I help you decide which distribution hubs are most exposed to weather disruption and should be
                  first in line for resilience upgrades. Ask me to rank hubs, compare them, or explain what drives
                  a hub's risk.
                </p>
                {turns.length === 0 && (
                  <div className="examples">
                    {EXAMPLES.map((e) => (
                      <button key={e.q} className="example" onClick={() => ask(e.q)}>
                        <span className="example-tag"><span aria-hidden>{e.icon}</span> {e.tag}</span>
                        {e.q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {turns.map((turn, i) => {
              if (turn.role === 'user') return <div key={i} className="msg user">{turn.text}</div>
              if (turn.role === 'agent') return <div key={i} className="msg agent"><AnswerCard reply={turn.reply} /></div>
              return (
                <div key={i} className="msg error" role="alert">
                  <span>Sorry, I couldn't answer that: {turn.text}</span>
                  <button className="ghost" onClick={() => ask(turn.retry)}>Try again</button>
                </div>
              )
            })}

            {pending && (
              <div className="msg agent thinking">
                <span className="dots" aria-hidden><i /><i /><i /></span>
                {AGENT_NAME} is checking the hub data…
              </div>
            )}
            <div ref={endRef} />
          </main>

          <form className="composer" onSubmit={onSubmit}>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={turns.length ? 'Ask a follow-up question…' : `Ask ${AGENT_NAME} about any hub…`}
              maxLength={2000}
              rows={1}
              disabled={pending}
              aria-label="Message"
            />
            <button type="submit" disabled={pending || !draft.trim()}>Send</button>
          </form>
          <p className="hint">Press Enter to send · Shift+Enter for a new line</p>
        </section>

        <RankingPanel onAskAbout={askAboutHub} disabled={pending} />
      </div>
    </div>
  )
}
