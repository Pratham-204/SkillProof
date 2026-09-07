import type { EvidenceType } from '../api'

// "Weak" means anything short of a real, commit-backed pass — CONTEXT.md's
// Declared-Only term exists specifically so `declared_only`/`none` can't be
// mistaken for a `verified` one. Centralized so both the reveal tile and
// search results branch on the exact same rule.
export function isWeakEvidence(evidenceType: EvidenceType): boolean {
  return evidenceType !== 'verified'
}

// Same dim-vs-lit treatment everywhere an Evidence Card renders (the reveal
// tile and search results) — the angular panel chrome itself comes from
// <StatusPanel>; this only adds the "dormant vs awakened" contrast on top of
// it, so a declared_only/no-evidence claim visibly reads as unlit.
//
// CSS `opacity` composites the whole panel (opaque background *and* the
// text/badge sitting on it) as one group before blending that group onto
// whatever is behind the panel — so the applied fraction dims the text
// exactly as much as the background, not just the chrome. At opacity-55 the
// evidenceTypeSummary copy (text-ink-dim, the exact "Declared in a
// manifest…" line a viewer needs to read) and the dim evidenceBadgeClassName
// pill land around 2.5:1 against the page background, under the 4.5:1 AA
// minimum for normal text. opacity-90 is the lowest step on Tailwind's
// scale that keeps every text/background pairing here above 4.5:1 even in
// the worst case (no opaque ancestor between this panel and --color-bg) —
// still visibly dimmer than a lit verified card, just not illegible.
export function evidenceCardClassName(isWeak: boolean): string {
  return `w-full p-4 text-left transition-opacity ${isWeak ? 'opacity-90' : ''}`
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

// Only "verified" gets the lit accent treatment — declared_only/none share
// the same quiet dim pill, since both are the isWeakEvidence(...) case above
// and neither should read as more credible than the other.
export function evidenceBadgeClassName(evidenceType: EvidenceType): string {
  const base = 'shrink-0 rounded-full border px-2.5 py-0.5 font-mono text-[0.65rem] uppercase tracking-wide'
  return evidenceType === 'verified'
    ? `${base} border-accent/40 bg-accent-soft text-accent-ink`
    : `${base} border-edge bg-surface-2 text-ink-dim`
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
