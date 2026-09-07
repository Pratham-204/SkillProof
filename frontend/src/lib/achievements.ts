import type { EvidenceCard } from '../api'
import { scoreToRank } from '../components/system/rank'

export interface Achievement {
  id: string
  label: string
  detail: string
}

// Every achievement here is a threshold over data the API already returns —
// nothing fabricated, nothing scored server-side. Purely a presentation-layer
// read of the same cards list the tile list already renders, the same way
// scoreToRank buckets confidence_score without changing what it means.
// Only cards that finished a real run count; a still-processing/failed card
// contributes to nothing.
export function computeAchievements(cards: EvidenceCard[]): Achievement[] {
  const complete = cards.filter((c) => c.status === 'complete')
  if (complete.length === 0) return []

  const verified = complete.filter((c) => c.evidence_type === 'verified')
  const totalEvidenceItems = complete.reduce((sum, c) => sum + c.source_commits.length, 0)
  // Private-repo refs all share one backend-redacted `repo` placeholder
  // (see EvidenceRef.private in api.ts), so they'd otherwise collapse onto a
  // single Set entry regardless of how many distinct private repos actually
  // back the evidence — undercounting diversity. Only public refs can be
  // told apart client-side, so only they count toward this achievement.
  const repos = new Set(
    complete.flatMap((c) => c.source_commits.filter((ref) => !ref.private).map((ref) => ref.repo)),
  )
  const longestSpan = Math.max(0, ...complete.map((c) => c.temporal_span_days))
  const hasSRank = complete.some((c) => scoreToRank(c.confidence_score, c.evidence_type) === 'S')

  const achievements: Achievement[] = []

  if (hasSRank) {
    achievements.push({
      id: 's-rank',
      label: 'S-Rank Hunter',
      detail: 'At least one claimed skill reached the top confidence tier.',
    })
  }
  if (verified.length === complete.length) {
    achievements.push({
      id: 'fully-verified',
      label: 'Fully Verified',
      detail: 'Every claimed skill is backed by real commit or PR evidence — none merely declared.',
    })
  }
  if (longestSpan >= 180) {
    achievements.push({
      id: 'long-hauler',
      label: 'Long Hauler',
      detail: `Evidence for at least one skill spans ${longestSpan}+ days — sustained use, not a weekend.`,
    })
  }
  if (totalEvidenceItems >= 15) {
    achievements.push({
      id: 'prolific',
      label: 'Prolific',
      detail: `${totalEvidenceItems} qualifying evidence items logged across every claimed skill.`,
    })
  }
  if (repos.size >= 3) {
    achievements.push({
      id: 'multi-repo',
      label: 'Multi-Repo',
      detail: `Evidence drawn from ${repos.size} distinct repositories.`,
    })
  }
  if (complete.length >= 5) {
    achievements.push({
      id: 'wide-range',
      label: 'Wide Range',
      detail: `${complete.length} skills claimed and scored in one hunter license.`,
    })
  }

  return achievements
}
