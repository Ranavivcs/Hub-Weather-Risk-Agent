import { AGENT_NAME } from './brand'
import { BANDS, HAZARD_BLURBS, HAZARD_ICONS, HAZARD_LABELS, HAZARDS } from './hazards'

/** "How we rank hubs": the scoring method in plain language for analysts (static content). */
export function MethodPanel() {
  return (
    <section className="side-section method">
      <p className="method-lead">
        Each hub gets a <strong>risk score from 0 to 100</strong>. Higher means weather is more likely to disrupt it.
      </p>

      <h3>Five hazards</h3>
      <ul className="hazard-list">
        {HAZARDS.map((h) => (
          <li key={h}>
            <span className="hazard-icon" aria-hidden>{HAZARD_ICONS[h]}</span>
            <span><strong>{HAZARD_LABELS[h]}</strong><span className="rank-sub">{HAZARD_BLURBS[h]}</span></span>
          </li>
        ))}
      </ul>

      <h3>How a score is built</h3>
      <ol className="steps">
        <li><strong>Past weather:</strong> how often the hub hit disruptive conditions in the last 5 years.</li>
        <li><strong>Official hazard records:</strong> how often each hazard is expected per year in the hub's area.</li>
        <li><strong>Overall score:</strong> the average of the five hazards, counted equally.</li>
      </ol>

      <h3>Score bands</h3>
      <div className="band-legend">
        {[...BANDS].reverse().map((b) => (
          <span key={b.key} className={`score band-${b.key} mini`}>{b.label}{b.min > 0 ? ` ${b.min}+` : ''}</span>
        ))}
      </div>

      <p className="method-note">
        A fixed formula calculates every score; {AGENT_NAME} only explains them. Scores compare exposure. They are
        not a forecast or a cost estimate.
      </p>
      <p className="side-foot">Hazard types: FEMA National Risk Index · Weather: Open-Meteo history</p>
    </section>
  )
}
