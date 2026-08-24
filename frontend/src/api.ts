// Thin fetch wrappers over the SkillProof API. The app is served single-origin
// (ADR-0006), so relative paths work in both `npm run build` (served by
// FastAPI) and `npm run dev` (proxied by Vite) without any base URL config.
// `credentials: 'same-origin'` sends the session cookie set at OAuth callback.

export interface Candidate {
  candidate_id: string
  github_login: string
  searchable: boolean
  needs_reconnect: boolean
}

export interface SkillTag {
  name: string
  category: string
  description: string
}

export interface EvidenceRef {
  kind: string
  repo: string
  ref: string
  url: string
  similarity: number
}

// "verified" (real commits touched it), "declared_only" (manifest lists it,
// never committed to), "none" (no evidence at all) — see CONTEXT.md's
// Declared-Only term. A real union, not a bare string, so a typo'd literal
// anywhere that branches on this is a compile error, not a silent no-match.
export type EvidenceType = 'verified' | 'declared_only' | 'none'

export interface EvidenceCard {
  skill: string
  status: string
  error: string | null
  confidence_score: number
  evidence_type: EvidenceType
  source_commits: EvidenceRef[]
  temporal_span_days: number
  taxonomy_version: number
  explanation: string | null
  explanation_is_fallback: boolean
}

export interface CandidateEvidence extends Candidate {
  cards: EvidenceCard[]
}

export interface SearchMatch {
  skill: string
  confidence_score: number
  evidence_type: EvidenceType
}

export interface SearchResult {
  candidate_id: string
  github_login: string
  github_profile_url: string
  evidence_card_url: string
  average_score: number
  matches: SearchMatch[]
}

/** Resolves the current session, or `null` if there isn't one (401) — never throws for that case. */
export async function getMe(): Promise<Candidate | null> {
  const response = await fetch('/auth/github/me', { credentials: 'same-origin' })
  if (response.status === 401) return null
  if (!response.ok) throw new Error(`GET /auth/github/me failed: ${response.status}`)
  return response.json()
}

export async function listSkills(): Promise<SkillTag[]> {
  const response = await fetch('/skills', { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`GET /skills failed: ${response.status}`)
  return response.json()
}

export async function verify(skills: string[], searchable: boolean): Promise<void> {
  const response = await fetch('/verify', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skills, searchable }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `POST /verify failed: ${response.status}`)
  }
}

export async function getEvidenceCard(candidateId: string): Promise<CandidateEvidence> {
  const response = await fetch(`/evidence-card/${candidateId}`, { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`GET /evidence-card/${candidateId} failed: ${response.status}`)
  return response.json()
}

export async function explainSkill(
  candidateId: string,
  skill: string,
): Promise<{ skill: string; explanation: string; explanation_is_fallback: boolean }> {
  const response = await fetch(`/explain/${candidateId}/${encodeURIComponent(skill)}`, {
    method: 'POST',
    credentials: 'same-origin',
  })
  if (!response.ok) throw new Error(`POST /explain/${candidateId}/${skill} failed: ${response.status}`)
  return response.json()
}

export async function searchCandidates(skills: string[]): Promise<SearchResult[]> {
  const params = new URLSearchParams()
  skills.forEach((skill) => params.append('skill', skill))
  const response = await fetch(`/search?${params}`, { credentials: 'same-origin' })
  if (response.status === 429) throw new RateLimitedError()
  if (!response.ok) throw new Error(`GET /search failed: ${response.status}`)
  const body = await response.json()
  return body.results
}

export class RateLimitedError extends Error {
  constructor() {
    super('Rate limited')
  }
}

export const GITHUB_LOGIN_URL = '/auth/github/login'
export const MAX_CLAIMED_SKILLS = 8
