import { describe, expect, it } from 'vitest'
import type { EvidenceCard } from '../api'
import { computeAchievements } from './achievements'

function card(overrides: Partial<EvidenceCard> = {}): EvidenceCard {
  return {
    skill: 'Python',
    status: 'complete',
    error: null,
    confidence_score: 0.5,
    evidence_type: 'verified',
    source_commits: [],
    temporal_span_days: 0,
    taxonomy_version: 1,
    explanation: null,
    explanation_is_fallback: false,
    ...overrides,
  }
}

describe('computeAchievements', () => {
  it('returns nothing for a candidate with no completed cards', () => {
    expect(computeAchievements([card({ status: 'processing' })])).toEqual([])
    expect(computeAchievements([])).toEqual([])
  })

  it('awards S-Rank Hunter only once a card clears the S threshold', () => {
    const below = computeAchievements([card({ confidence_score: 0.84 })])
    expect(below.find((a) => a.id === 's-rank')).toBeUndefined()

    const at = computeAchievements([card({ confidence_score: 0.85 })])
    expect(at.find((a) => a.id === 's-rank')).toBeDefined()
  })

  it('awards Fully Verified only when every completed card is verified', () => {
    const mixed = computeAchievements([card({ evidence_type: 'verified' }), card({ evidence_type: 'declared_only' })])
    expect(mixed.find((a) => a.id === 'fully-verified')).toBeUndefined()

    const allVerified = computeAchievements([card({ evidence_type: 'verified' }), card({ evidence_type: 'verified' })])
    expect(allVerified.find((a) => a.id === 'fully-verified')).toBeDefined()
  })

  it('ignores a processing/failed card when checking Fully Verified, not just when counting it', () => {
    // A still-processing card must not silently count as "verified" and
    // must not block the achievement either — it should be excluded outright.
    const result = computeAchievements([card({ evidence_type: 'verified' }), card({ status: 'processing' })])
    expect(result.find((a) => a.id === 'fully-verified')).toBeDefined()
  })

  it('awards Long Hauler at the 180-day threshold', () => {
    expect(computeAchievements([card({ temporal_span_days: 179 })]).find((a) => a.id === 'long-hauler')).toBeUndefined()
    expect(computeAchievements([card({ temporal_span_days: 180 })]).find((a) => a.id === 'long-hauler')).toBeDefined()
  })

  it('awards Multi-Repo counting distinct repos across all cards, not per-card', () => {
    const ref = (repo: string) => ({ kind: 'commit', repo, ref: 'abc', url: '', similarity: 0.5, private: false })
    const result = computeAchievements([
      card({ source_commits: [ref('a'), ref('b')] }),
      card({ source_commits: [ref('c')] }),
    ])
    expect(result.find((a) => a.id === 'multi-repo')).toBeDefined()
  })

  it('does not award Multi-Repo from private-repo evidence alone, even across distinct private repos', () => {
    // The backend redacts every private ref's `repo` to the same placeholder
    // string regardless of which actual private repo it came from, so the
    // frontend cannot tell 3 distinct private repos apart from 1 — only
    // public refs can contribute to this count.
    const privateRef = { kind: 'commit', repo: 'a private repository', ref: 'abc', url: '', similarity: 0.5, private: true }
    const result = computeAchievements([
      card({ source_commits: [privateRef] }),
      card({ source_commits: [privateRef] }),
      card({ source_commits: [privateRef] }),
    ])
    expect(result.find((a) => a.id === 'multi-repo')).toBeUndefined()
  })

  it('awards Wide Range at 5 completed skills', () => {
    const four = computeAchievements(Array.from({ length: 4 }, () => card()))
    expect(four.find((a) => a.id === 'wide-range')).toBeUndefined()

    const five = computeAchievements(Array.from({ length: 5 }, () => card()))
    expect(five.find((a) => a.id === 'wide-range')).toBeDefined()
  })
})
