import { useEffect, useRef, useState, type FormEvent } from 'react'
import { AnswerCard } from './AnswerCard'
import { sendChat, type ChatResponse } from './api'
import './App.css'

type Turn = { role: 'user'; text: string } | { role: 'agent'; reply: ChatResponse } | { role: 'error'; text: string }

const EXAMPLES = [
  'Which hubs in the Midwest are most exposed to winter disruption?',
  'Compare Miami and Houston in terms of hurricane and flood exposure.',
  'What percentage of days in Denver last year had snowfall?',
  "Why is the Dallas hub's weather disruption risk high?",
]

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  // Scroll to the newest message only when the list changes.
  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [turns])

  async function ask(text: string) {
    const message = text.trim()
    if (!message || pending) return
    setTurns((t) => [...t, { role: 'user', text: message }])
    setDraft('')
    setPending(true)
    try {
      const reply = await sendChat(message, conversationId)
      setConversationId(reply.conversation_id)
      setTurns((t) => [...t, { role: 'agent', reply }])
    } catch (err) {
      setTurns((t) => [...t, { role: 'error', text: (err as Error).message }])
    } finally {
      setPending(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    ask(draft)
  }

  function newConversation() {
    setTurns([])
    setConversationId(null)
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Hub Weather Risk Agent</h1>
          <p className="muted">
            Ranks 15 US distribution hubs by weather exposure (Open-Meteo 2021–2025 + FEMA National Risk Index).
          </p>
        </div>
        <button className="secondary" onClick={newConversation} disabled={pending || turns.length === 0}>
          New conversation
        </button>
      </header>

      <main className="chat">
        {turns.length === 0 && (
          <div className="examples">
            <p className="muted">Try one of these, then ask follow-up questions:</p>
            {EXAMPLES.map((q) => (
              <button key={q} className="example" onClick={() => ask(q)}>{q}</button>
            ))}
          </div>
        )}
        {turns.map((turn, i) =>
          turn.role === 'user' ? <div key={i} className="msg user">{turn.text}</div>
          : turn.role === 'agent' ? <div key={i} className="msg agent"><AnswerCard reply={turn.reply} /></div>
          : <div key={i} className="msg error">⚠ {turn.text}</div>,
        )}
        {pending && <div className="msg agent muted">Analyzing hub data…</div>}
        <div ref={endRef} />
      </main>

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about hub weather exposure…"
          maxLength={2000}
          disabled={pending}
        />
        <button type="submit" disabled={pending || !draft.trim()}>Send</button>
      </form>
    </div>
  )
}
