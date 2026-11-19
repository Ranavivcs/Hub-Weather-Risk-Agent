import { band } from './hazards'

/** A 0-100 score with its band colour. The number is always printed, so colour is never the only signal. */
export function ScoreCell({ score, emphasis = false }: { score: number; emphasis?: boolean }) {
  const b = band(score)
  return (
    <span className={`score band-${b.key} ${emphasis ? 'emphasis' : ''}`} title={`${b.label} (${score.toFixed(1)})`}>
      {score.toFixed(0)}
    </span>
  )
}
