// Shared "weak evidence" card treatment — CONTEXT.md's Declared-Only term
// exists specifically so a `declared_only`/`none` card can't be mistaken for
// a real `verified` pass, so this same dashed/muted-vs-solid distinction is
// used everywhere an Evidence Card renders (the reveal tile and search results).
export function evidenceCardClassName(isWeak: boolean): string {
  return `rounded-xl border p-4 text-left ${
    isWeak
      ? 'border-dashed border-neutral-300 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900/40'
      : 'border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900'
  }`
}
