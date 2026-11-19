import type { ChatResponse } from './api'
import { HAZARD_ICONS, HAZARD_LABELS, HAZARDS, TOOL_LABELS } from './hazards'
import { RichText } from './RichText'
import { ScoreCell } from './ScoreCell'
import { splitTakeaway } from './text'

const STATUS_LABELS = { out_of_scope: 'Outside what I cover', needs_clarification: 'Need a bit more detail' } as const

/** One agent reply: takeaway, reasoning, the formula-computed scores of the hubs it names, then caveats. */
export function AnswerCard({ reply }: { reply: ChatResponse }) {
  const { answer, hub_scores, tools_used } = reply
  const [takeaway, rest] = splitTakeaway(answer.answer)
  const sources = [...new Set(tools_used)].map((t) => TOOL_LABELS[t] ?? t)
  const caveats = answer.assumptions.length + answer.uncertainty.length

  return (
    <article className="answer">
      {answer.status !== 'answered' && <span className="status">{STATUS_LABELS[answer.status]}</span>}
      <p className="takeaway">{takeaway}</p>
      {rest && <RichText text={rest} />}

      {hub_scores.length > 0 && (
        <section className="score-block" aria-label="Risk scores">
          <div className="score-scroll">
            <table className="scores">
              <thead>
                <tr>
                  <th>Hub</th>
                  <th className="num">Overall</th>
                  {HAZARDS.map((h) => (
                    <th key={h} className={`num ${answer.hazards.includes(h) ? 'focus' : ''}`}>
                      <span aria-hidden>{HAZARD_ICONS[h]}</span> {HAZARD_LABELS[h]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {hub_scores.map((s) => (
                  <tr key={s.hub_id}>
                    <td>
                      <span className="hub-name">{s.name}</span>
                      <span className="hub-rank">#{s.composite_rank} overall</span>
                    </td>
                    <td className="num"><ScoreCell score={s.composite} emphasis /></td>
                    {HAZARDS.map((h) => (
                      <td key={h} className={`num ${answer.hazards.includes(h) ? 'focus' : ''}`}>
                        <ScoreCell score={s.hazards[h]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="legend">Score 0–100 · higher = more exposed · calculated by a fixed formula, not the AI</p>
        </section>
      )}

      {(caveats > 0 || sources.length > 0) && (
        <footer className="answer-footer">
          {caveats > 0 && (
            <details className="notes">
              <summary>Assumptions and data limits ({caveats})</summary>
              {answer.assumptions.length > 0 && <NoteList title="Assumptions" items={answer.assumptions} />}
              {answer.uncertainty.length > 0 && <NoteList title="Data limits" items={answer.uncertainty} />}
            </details>
          )}
          {sources.length > 0 && <span className="sources">Based on: {sources.join(' · ')}</span>}
        </footer>
      )}
    </article>
  )
}

function NoteList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="note-group">
      <h4>{title}</h4>
      <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </div>
  )
}
