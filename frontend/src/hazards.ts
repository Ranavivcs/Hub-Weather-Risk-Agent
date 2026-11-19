import type { Hazard } from './api'

export const HAZARD_LABELS: Record<Hazard, string> = {
  winter: 'Winter',
  hurricane: 'Hurricane',
  flood: 'Flood',
  heat: 'Heat',
  severe_storm: 'Severe storm',
}

export const HAZARD_ICONS: Record<Hazard, string> = {
  winter: '❄️',
  hurricane: '🌀',
  flood: '🌊',
  heat: '🔥',
  severe_storm: '⛈️',
}

/** Plain-language description of what each hazard covers (for the "How we rank" panel). */
export const HAZARD_BLURBS: Record<Hazard, string> = {
  winter: 'Snow, icy roads and freezing cold',
  hurricane: 'Huge ocean storms that hit the coast',
  flood: 'Heavy rain, and rivers or the sea overflowing',
  heat: 'Very hot days and heat waves',
  severe_storm: 'Sudden thunderstorms: tornadoes, hail, strong wind',
}

export const HAZARDS = Object.keys(HAZARD_LABELS) as Hazard[]

/** Customer-facing names for the agent's tools, shown under "How I answered". */
export const TOOL_LABELS: Record<string, string> = {
  list_hubs: 'Hub list',
  rank_hubs: 'Hub ranking',
  hub_breakdown: 'Score breakdown',
  compare_hubs: 'Side-by-side comparison',
  weather_stats: 'Historical weather records',
}

/** Display bands for a 0-100 score. Only for colour; the number is always shown next to it. */
export const BANDS = [
  { min: 75, key: 'very-high', label: 'Very high' },
  { min: 50, key: 'high', label: 'High' },
  { min: 25, key: 'moderate', label: 'Moderate' },
  { min: 0, key: 'low', label: 'Low' },
] as const

export function band(score: number): (typeof BANDS)[number] {
  return BANDS.find((b) => score >= b.min) ?? BANDS[BANDS.length - 1]
}
