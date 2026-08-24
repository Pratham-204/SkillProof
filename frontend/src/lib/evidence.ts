import type { EvidenceType } from '../api'

// "Weak" means anything short of a real, commit-backed pass — CONTEXT.md's
// Declared-Only term exists specifically so `declared_only`/`none` can't be
// mistaken for a `verified` one. Centralized so both the reveal tile and
// search results branch on the exact same rule.
export function isWeakEvidence(evidenceType: EvidenceType): boolean {
  return evidenceType !== 'verified'
}

// Same dashed/muted-vs-solid card treatment everywhere an Evidence Card
// renders (the reveal tile and search results).
export function evidenceCardClassName(isWeak: boolean): string {
  return `rounded-xl border p-4 text-left ${
    isWeak
      ? 'border-dashed border-neutral-300 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900/40'
      : 'border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900'
  }`
}

// One switch over EvidenceType instead of one per caller. `qualifyingItemCount`
// is only meaningful for "verified" (it's `source_commits.length`, the count of
// Depth-qualifying items — see EvidenceCardTile's fuller wording); callers that
// don't have that count (search results only get evidence_type, not the full
// card) omit it and get a plain "Verified" label instead.
export function evidenceTypeSummary(evidenceType: EvidenceType, qualifyingItemCount?: number): string {
  switch (evidenceType) {
    case 'verified':
      if (qualifyingItemCount === undefined) return 'Verified'
      return qualifyingItemCount > 0
        ? `${qualifyingItemCount} evidence item${qualifyingItemCount === 1 ? '' : 's'} matched closely enough for Depth`
        : 'Real commits found, but none closely matched the skill description'
    case 'declared_only':
      return 'Declared in a manifest — never touched in a commit'
    case 'none':
      return 'No evidence found'
  }
}
