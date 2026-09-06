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

// Compact pill label for evidence_type, shown next to the skill name — the
// dashed/solid card treatment above signals "weak vs. not" at a glance across
// a whole list, this pill names the exact state on a single card.
export function evidenceBadgeLabel(evidenceType: EvidenceType): string {
  switch (evidenceType) {
    case 'verified':
      return 'Verified'
    case 'declared_only':
      return 'Declared only'
    case 'none':
      return 'No evidence'
  }
}

// Only "verified" gets the accent treatment — declared_only/none share the
// same quiet neutral pill, since both are the isWeakEvidence(...) case above
// and neither should read as more credible than the other.
export function evidenceBadgeClassName(evidenceType: EvidenceType): string {
  const base = 'shrink-0 rounded-full px-2.5 py-0.5 font-mono text-[0.65rem] uppercase tracking-wide'
  return evidenceType === 'verified'
    ? `${base} bg-accent-soft text-accent-ink`
    : `${base} bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400`
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
