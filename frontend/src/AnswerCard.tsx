import type { ChatResponse, Hazard } from './api'

const HAZARD_LABELS: Record<Hazard, string> = {
  winter: 'Winter',
  hurricane: 'Hurricane',
  flood: 'Flood',
  heat: 'Heat',
  severe_storm: 'Severe storm',
}
const HAZARDS = Object.keys(HAZARD_LABELS) as Hazard[]

const STATUS_LABELS = { out_of_scope: 'Out of scope', needs_clarification: 'Needs clarification' } as const

/** One agent reply: the answer text, the code-computed scores for the hubs it names, and its caveats. */
export function AnswerCard({ reply }: { reply: ChatResponse }) {
  const { answer, hub_scores, tools_used } = reply
  return (
    <div className="answer">
      {answer.status !== 'answered' && <span className="badge">{STATUS_LABELS[answer.status]}</span>}
      <p className="answer-text">{answer.answer}</p>

      {hub_scores.length > 0 && (
        <table className="scores">
          <caption>Risk scores (0–100, higher = more exposed), computed by the scoring code</caption>
          <thead>
            <tr>
              <th>Hub</th>
              <th>Composite</th>
              {HAZARDS.map((h) => <th key={h}>{HAZARD_LABELS[h]}</th>)}
            </tr>
          </thead>
          <tbody>
            {hub_scores.map((s) => (
              <tr key={s.hub_id}>
                <td>{s.name}, {s.state}<div className="muted">composite rank #{s.composite_rank}</div></td>
                <td className="num strong">{s.composite.toFixed(1)}</td>
                {HAZARDS.map((h) => (
                  <td key={h} className={`num ${answer.hazards.includes(h) ? 'focus' : ''}`}>
                    <span className="bar" style={{ width: `${s.hazards[h]}%` }} />
                    {s.hazards[h].toFixed(0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Notes title="Assumptions" items={answer.assumptions} />
      <Notes title="Uncertainty" items={answer.uncertainty} />
      {tools_used.length > 0 && <div className="muted tools">Tools used: {tools_used.join(', ')}</div>}
    </div>
  )
}

function Notes({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <details className="notes">
      <summary>{title} ({items.length})</summary>
      <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </details>
  )
}
