import type { ChatResponse } from './api'
import { HAZARD_ICONS, HAZARD_LABELS, HAZARDS, TOOL_LABELS } from './hazards'
import { RichText } from './RichText'
import { ScoreCell } from './ScoreCell'

const STATUS_LABELS = { out_of_scope: 'Outside what I cover', needs_clarification: 'Need a bit more detail' } as const

/** One agent reply: the answer, the formula-computed scores of the hubs it names, and its caveats. */
export function AnswerCard({ reply }: { reply: ChatResponse }) {
  const { answer, hub_scores, tools_used } = reply
  const sources = [...new Set(tools_used)].map((t) => TOOL_LABELS[t] ?? t)
  return (
    <article className="answer">
      {answer.status !== 'answered' && <span className="status">{STATUS_LABELS[answer.status]}</span>}
      {answer.hazards.length > 0 && (
        <div className="chips">
          {answer.hazards.map((h) => <span key={h} className="chip">{HAZARD_ICONS[h]} {HAZARD_LABELS[h]}</span>)}
        </div>
      )}

      <RichText text={answer.answer} />

      {hub_scores.length > 0 && (
        <section className="score-block">
          <div className="score-scroll">
            <table className="scores">
              <thead>
                <tr>
                  <th>Hub</th>
                  <th className="num">Overall</th>
                  {HAZARDS.map((h) => (
                    <th key={h} className="num"><span aria-hidden>{HAZARD_ICONS[h]}</span> {HAZARD_LABELS[h]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {hub_scores.map((s) => (
                  <tr key={s.hub_id}>
                    <td>
                      <div className="hub-name">{s.name}, {s.state}</div>
                      <div className="sub">Ranked #{s.composite_rank} overall</div>
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
          <div className="legend">Risk score 0–100 · higher means more exposed · calculated by a fixed formula</div>
        </section>
      )}

      {(answer.assumptions.length > 0 || answer.uncertainty.length > 0 || sources.length > 0) && (
        <footer className="answer-footer">
          <Notes title="Assumptions" items={answer.assumptions} />
          <Notes title="Data limitations" items={answer.uncertainty} />
          {sources.length > 0 && <div className="tools">How I answered: {sources.join(' · ')}</div>}
        </footer>
      )}
    </article>
  )
}

function Notes({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <details className="notes">
      <summary>{title} <span className="count">{items.length}</span></summary>
      <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </details>
  )
}
