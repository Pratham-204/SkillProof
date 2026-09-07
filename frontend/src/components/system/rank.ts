import type { EvidenceType } from '../../api'

// Presentation-only: Hunter Rank is a client-side bucketing of the existing
// confidence_score (see CONTEXT.md's Confidence Score term) into the E-S
// scale of the Status Window theme. It changes nothing about scoring, is
// derived fresh from data the API already returns, and is never persisted.
export type RankLetter = 'E' | 'D' | 'C' | 'B' | 'A' | 'S'

export function scoreToRank(score: number, evidenceType: EvidenceType): RankLetter {
  if (evidenceType === 'none' || score <= 0) return 'E'
  if (score >= 0.85) return 'S'
  if (score >= 0.7) return 'A'
  if (score >= 0.5) return 'B'
  if (score >= 0.3) return 'C'
  return 'D'
}

export interface RankTheme {
  ink: string
  glow: string
}

// Escalating from a dim, barely-lit gray-blue (E — an unawakened claim) up
// through the System's signature cyan to gold at S rank, the one color in
// the whole system reserved for the top tier.
export const RANK_THEME: Record<RankLetter, RankTheme> = {
  E: { ink: '#5b6b85', glow: 'rgba(91,107,133,.25)' },
  D: { ink: '#5fa9d6', glow: 'rgba(95,169,214,.3)' },
  C: { ink: '#4dd8ff', glow: 'rgba(77,216,255,.38)' },
  B: { ink: '#7fe4ff', glow: 'rgba(127,228,255,.45)' },
  A: { ink: '#aef0ff', glow: 'rgba(174,240,255,.55)' },
  S: { ink: '#ffd76a', glow: 'rgba(255,215,106,.6)' },
}
