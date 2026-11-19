// Types mirror app/schemas.py (the backend is the source of truth).

export type Hazard = 'winter' | 'hurricane' | 'flood' | 'heat' | 'severe_storm'

export interface AgentAnswer {
  status: 'answered' | 'out_of_scope' | 'needs_clarification'
  answer: string
  hub_ids: string[]
  hazards: Hazard[]
  assumptions: string[]
  uncertainty: string[]
}

export interface HubScore {
  hub_id: string
  name: string
  state: string
  region: string
  composite: number
  composite_rank: number
  hazards: Record<Hazard, number>
  top_drivers: Hazard[]
}

export interface ChatResponse {
  conversation_id: string
  answer: AgentAnswer
  hub_scores: HubScore[]
  tools_used: string[]
}

/** POST /api/chat: send one message; pass the conversation id back for follow-ups (null starts a new one). */
export async function sendChat(message: string, conversationId: string | null): Promise<ChatResponse> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${res.status})`)
  }
  return res.json()
}
