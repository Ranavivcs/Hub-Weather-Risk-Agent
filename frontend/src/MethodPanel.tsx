import { AGENT_NAME } from './brand'
import { BANDS, HAZARD_BLURBS, HAZARD_ICONS, HAZARD_LABELS, HAZARDS } from './hazards'

/** "How we rank hubs": the scoring method in plain language for analysts (static content). */
export function MethodPanel() {
  return (
    <aside className="panel method">
      <h2>How we rank hubs</h2>
      <p className="lead">
        Every hub gets a <strong>risk score from 0 to 100</strong>. The higher the score, the more often weather
        is likely to disrupt that hub.
      </p>

      <h3>Five weather hazards</h3>
      <ul className="hazard-list">
        {HAZARDS.map((h) => (
          <li key={h}>
            <span className="hazard-icon" aria-hidden>{HAZARD_ICONS[h]}</span>
            <span><strong>{HAZARD_LABELS[h]}</strong><span className="sub">{HAZARD_BLURBS[h]}</span></span>
          </li>
        ))}
      </ul>
      <p className="hazard-source">Hazard types follow the U.S. government's FEMA National Risk Index.</p>

      <h3>What goes into a score</h3>
      <ol className="steps">
        <li><strong>Past weather</strong>: how often the hub actually hit disruptive conditions in the last 5 years.</li>
        <li><strong>Official hazard records</strong>: how often each hazard is expected per year in the hub's area.</li>
        <li>The <strong>overall score</strong> is the average of the five hazards, each counted equally.</li>
      </ol>

      <h3>Reading the scores</h3>
      <div className="band-legend">
        {[...BANDS].reverse().map((b) => (
          <span key={b.key} className={`score band-${b.key} mini`}>{b.label}{b.min > 0 ? ` ${b.min}+` : ''}</span>
        ))}
      </div>

      <p className="note">
        Scores are calculated by a fixed formula, not by the AI; {AGENT_NAME} explains them. Scores compare how exposed
        hubs are; they are not a forecast or a cost estimate.
      </p>
      <p className="source">Data: Open-Meteo weather history · FEMA National Risk Index</p>
    </aside>
  )
}
