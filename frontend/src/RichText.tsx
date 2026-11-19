/** Render the agent's plain text: blank-line paragraphs, and lines starting with "- " as bullet lists.
 *  Builds React elements (no HTML injection), so model output can't inject markup. */
export function RichText({ text }: { text: string }) {
  const blocks: { kind: 'p' | 'ul'; lines: string[] }[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const kind = line.startsWith('- ') ? 'ul' : 'p'
    if (!line) {
      blocks.push({ kind: 'p', lines: [] }) // paragraph break
      continue
    }
    const last = blocks[blocks.length - 1]
    if (last && last.kind === kind && last.lines.length > 0) last.lines.push(kind === 'ul' ? line.slice(2) : line)
    else blocks.push({ kind, lines: [kind === 'ul' ? line.slice(2) : line] })
  }
  return (
    <div className="rich">
      {blocks.filter((b) => b.lines.length > 0).map((b, i) =>
        b.kind === 'ul'
          ? <ul key={i}>{b.lines.map((l, j) => <li key={j}>{l}</li>)}</ul>
          : <p key={i}>{b.lines.join(' ')}</p>,
      )}
    </div>
  )
}
