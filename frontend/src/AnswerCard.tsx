import type { ChatResponse } from './api'
import { HAZARD_ICONS, HAZARD_LABELS, HAZARDS, TOOL_LABELS } from './hazards'
import { RichText } from './RichText'
import { ScoreCell } from './ScoreCell'

const STATUS_LABELS = { out_of_scope: 'Outside what I cover', needs_clarification: 'Need a bit more detail' } as const

/** One agent reply: reasoning, the formula-computed scores of the hubs it names, the bottom line, then caveats. */
export function AnswerCard({ reply }: { reply: ChatResponse }) {
  const { answer, hub_scores, tools_used } = reply
  const sources = [...new Set(tools_used)].map((t) => TOOL_LABELS[t] ?? t)
  const caveats = answer.assumptions.length + answer.uncertainty.length

  return (
    <article className="answer">
      {answer.status !== 'answered' && <span className="status">{STATUS_LABELS[answer.status]}</span>}
      <RichText text={answer.answer} />

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

      <p className="bottom-line"><span className="bottom-line-label">Bottom line</span>{answer.bottom_line}</p>

      {(caveats > 0 || sources.length > 0) && (
        <footer className="answer-footer">
          <Notes title="Assumptions" items={answer.assumptions} />
          <Notes title="Data limitations" items={answer.uncertainty} />
          {sources.length > 0 && <span className="sources">Based on: {sources.join(' · ')}</span>}
        </footer>
      )}
    </article>
  )
}

/** A collapsed list (assumptions or data limitations), shown only when it has items. */
function Notes({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <details className="notes">
      <summary>{title} <span className="count">{items.length}</span></summary>
      <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </details>
  )
}
