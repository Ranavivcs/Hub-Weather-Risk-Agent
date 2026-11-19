import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { AnswerCard } from './AnswerCard'
import { sendChat, type ChatResponse, type HubScore } from './api'
import { AGENT_NAME } from './brand'
import { Sidebar } from './Sidebar'
import { useSpeechInput } from './useSpeechInput'
import './App.css'

type Turn =
  | { role: 'user'; text: string }
  | { role: 'agent'; reply: ChatResponse }
  | { role: 'error'; text: string; retry: string }

const EXAMPLES = [
  { icon: '❄️', q: 'Which hubs in the Midwest are most exposed to winter disruption?' },
  { icon: '🌀', q: 'Compare Miami and Houston in terms of hurricane and flood exposure.' },
  { icon: '📅', q: 'What percentage of days in Denver last year had snowfall?' },
  { icon: '🔎', q: "Why is the Dallas hub's weather disruption risk high?" },
]

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false) // sidebar drawer on narrow screens
  const endRef = useRef<HTMLDivElement>(null)
  const voice = useSpeechInput(setDraft)

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
    setMenuOpen(false)
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

  function newConversation() {
    setTurns([])
    setConversationId(null)
    setMenuOpen(false)
  }

  return (
    <div className="shell">
      <Sidebar
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onAskAbout={askAboutHub}
        onNewConversation={newConversation}
        busy={pending}
        canReset={turns.length > 0}
      />
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden />}

      <div className="main">
        <header className="mobile-bar">
          <button className="menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu">☰</button>
          <span className="brand-name">{AGENT_NAME}</span>
        </header>

        <main className="chat" aria-live="polite">
          <section className="hero">
            <div className="avatar" aria-hidden>🛰️</div>
            <h1>Hi, I'm {AGENT_NAME}, your weather risk agent.</h1>
            <p>
              I help you find which distribution hubs are most exposed to weather disruption, so you know where
              resilience upgrades pay off first. Ask me to rank, compare or explain hubs.
            </p>
            {turns.length === 0 && (
              <div className="starters">
                {EXAMPLES.map((e) => (
                  <button key={e.q} className="starter" onClick={() => ask(e.q)}>
                    <span aria-hidden>{e.icon}</span> {e.q}
                  </button>
                ))}
              </div>
            )}
          </section>

          {turns.map((turn, i) => {
            if (turn.role === 'user') return <div key={i} className="msg user">{turn.text}</div>
            if (turn.role === 'agent') {
              return (
                <div key={i} className="msg agent">
                  <div className="avatar small" aria-hidden>🛰️</div>
                  <AnswerCard reply={turn.reply} />
                </div>
              )
            }
            return (
              <div key={i} className="msg error" role="alert">
                <span>Sorry, I couldn't answer that: {turn.text}</span>
                <button className="link" onClick={() => ask(turn.retry)}>Try again</button>
              </div>
            )
          })}

          {pending && (
            <div className="msg agent thinking">
              <div className="avatar small" aria-hidden>🛰️</div>
              <span className="dots" aria-hidden><i /><i /><i /></span>
              {AGENT_NAME} is checking the hub data…
            </div>
          )}
          <div ref={endRef} />
        </main>

        <div className="composer-wrap">
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
            {voice.supported && (
              <button
                type="button"
                className={`mic ${voice.listening ? 'listening' : ''}`}
                onClick={() => (voice.listening ? voice.stop() : voice.start(draft.trim()))}
                disabled={pending}
                aria-label={voice.listening ? 'Stop voice input' : 'Speak your question'}
                title={voice.listening ? 'Stop listening' : 'Speak your question'}
              >
                {voice.listening ? '■' : '🎤'}
              </button>
            )}
            <button type="submit" className="send" disabled={pending || !draft.trim()}>Send</button>
          </form>
          <p className="hint">
            {voice.error ?? (voice.listening
              ? 'Listening… speak your question, then press Send'
              : `Enter to send · Shift+Enter for a new line${voice.supported ? ' · 🎤 to speak' : ''}`)}
          </p>
        </div>
      </div>
    </div>
  )
}
