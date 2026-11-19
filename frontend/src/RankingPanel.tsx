import { useEffect, useState } from 'react'
import { AGENT_NAME } from './brand'
import { fetchHubs, type Hazard, type HubScore } from './api'
import { HAZARD_ICONS, HAZARD_LABELS, HAZARDS } from './hazards'
import { ScoreCell } from './ScoreCell'

/** All hubs ranked by the deterministic score (GET /api/hubs). Fetched when the sort changes, not polled. */
export function RankingPanel({ onAskAbout, disabled }: { onAskAbout: (hub: HubScore) => void; disabled: boolean }) {
  const [hazard, setHazard] = useState<Hazard | null>(null)
  const [hubs, setHubs] = useState<HubScore[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchHubs(hazard)
      .then((data) => { if (!cancelled) { setHubs(data); setError(null) } })
      .catch((err: Error) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true } // ignore a slower, outdated response
  }, [hazard])

  return (
    <aside className="panel ranking">
      <div className="panel-head">
        <h2>Most exposed hubs</h2>
        <select value={hazard ?? ''} onChange={(e) => setHazard((e.target.value || null) as Hazard | null)} aria-label="Rank by">
          <option value="">Overall risk</option>
          {HAZARDS.map((h) => <option key={h} value={h}>{HAZARD_ICONS[h]} {HAZARD_LABELS[h]}</option>)}
        </select>
      </div>
      {error && <p className="panel-error">{error}</p>}
      <ol className="rank-list">
        {hubs.map((h, i) => (
          <li key={h.hub_id}>
            <button className="rank-row" onClick={() => onAskAbout(h)} disabled={disabled}
                    title={`Ask ${AGENT_NAME} about ${h.name}`}>
              <span className="rank-pos">{i + 1}</span>
              <span className="rank-name">{h.name}<span className="sub">{h.state} · {h.region}</span></span>
              <span className="rank-ask" aria-hidden>Ask →</span>
              <ScoreCell score={hazard ? h.hazards[hazard] : h.composite} />
            </button>
          </li>
        ))}
      </ol>
      <p className="panel-foot">Click any hub to ask {AGENT_NAME} what drives its score.</p>
    </aside>
  )
}
