/** Split off the first sentence of an answer as its takeaway. A sentence ends at . ! ? followed by a space and
 *  a capital letter, so decimals like "77.7" don't split. Returns [takeaway, rest]. */
export function splitTakeaway(text: string): [string, string] {
  const trimmed = text.trim()
  const m = trimmed.match(/^([\s\S]*?[.!?])\s+(?=[A-Z])/)
  if (!m || m[1].includes('\n')) return [trimmed, '']
  return [m[1], trimmed.slice(m[0].length)]
}
