import { motion } from 'framer-motion'
import { useState } from 'react'
import { explainSkill, type EvidenceCard } from '../api'
import ScoreCounter from './ScoreCounter'

const cardVariants = {
  hidden: { opacity: 0, y: 16, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1 },
}

interface EvidenceCardTileProps {
  card: EvidenceCard
  /** Needed to call POST /explain/{candidateId}/{skill} lazily on expand. */
  candidateId: string
}

// evidence_type gets a visibly distinct treatment on purpose — CONTEXT.md's
// Declared-Only term exists specifically so a Recruiter (or the Candidate
// themselves) can't mistake a bare manifest listing for real usage history.
export default function EvidenceCardTile({ card, candidateId }: EvidenceCardTileProps) {
  const [expanded, setExpanded] = useState(false)
  const [explanation, setExplanation] = useState<string | null>(card.explanation)
  const [isFallback, setIsFallback] = useState(card.explanation_is_fallback)
  const [explaining, setExplaining] = useState(false)
  const [explainError, setExplainError] = useState<string | null>(null)

  if (card.status === 'failed') {
    return (
      <motion.li
        variants={cardVariants}
        className="rounded-xl border border-red-300 bg-red-50 p-4 text-left dark:border-red-900 dark:bg-red-950/40"
      >
        <p className="font-medium">{card.skill}</p>
        <p className="mt-1 text-sm text-red-700 dark:text-red-400">{card.error ?? 'Verification failed.'}</p>
      </motion.li>
    )
  }

  const isWeak = card.evidence_type !== 'verified'

  // Fetched once per mount, then held in this tile's own state — re-expanding
  // the same (still-mounted) card never re-fetches on top of the backend's
  // own server-side cache on the Evidence Card.
  function handleToggle() {
    const opening = !expanded
    setExpanded(opening)
    if (opening && explanation === null && !explaining) {
      setExplaining(true)
      setExplainError(null)
      explainSkill(candidateId, card.skill)
        .then((res) => {
          setExplanation(res.explanation)
          setIsFallback(res.explanation_is_fallback)
        })
        .catch((err) => setExplainError(err instanceof Error ? err.message : 'Could not load explanation.'))
        .finally(() => setExplaining(false))
    }
  }

  return (
    <motion.li
      variants={cardVariants}
      className={`rounded-xl border p-4 text-left ${
        isWeak
          ? 'border-dashed border-neutral-300 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900/40'
          : 'border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900'
      }`}
    >
      <button type="button" onClick={handleToggle} className="flex w-full items-start justify-between gap-3 text-left">
        <p className="font-medium">{card.skill}</p>
        <ScoreCounter score={card.confidence_score} className={`text-lg ${isWeak ? 'opacity-60' : ''}`} />
      </button>
      <p className={`mt-1 text-xs ${isWeak ? 'text-neutral-500' : 'text-neutral-600 dark:text-neutral-400'}`}>
        {card.evidence_type === 'verified' &&
          (card.source_commits.length > 0
            ? `${card.source_commits.length} evidence item${card.source_commits.length === 1 ? '' : 's'} matched closely enough for Depth`
            : 'Real commits found, but none closely matched the skill description')}
        {card.evidence_type === 'declared_only' && 'Declared in a manifest — never touched in a commit'}
        {card.evidence_type === 'none' && 'No evidence found'}
      </p>

      {expanded && (
        <div className="mt-3 flex flex-col gap-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          {card.source_commits.length > 0 && (
            <ul className="flex flex-col gap-1">
              {card.source_commits.map((ref) => (
                <li key={`${ref.kind}-${ref.ref}`} className="font-mono text-xs">
                  <a href={ref.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:opacity-70">
                    {ref.kind === 'commit' ? 'commit' : 'PR comment'} {ref.ref.slice(0, 7)}
                  </a>
                  <span className="ml-2 text-neutral-400">{ref.repo}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="text-sm">
            {explaining && <p className="text-neutral-400 italic">Generating explanation…</p>}
            {explainError && <p className="text-red-600 dark:text-red-400">{explainError}</p>}
            {explanation && (
              <p>
                {explanation}
                {isFallback && (
                  <span className="ml-2 rounded-full bg-neutral-200 px-2 py-0.5 text-[0.65rem] font-medium text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                    template fallback
                  </span>
                )}
              </p>
            )}
          </div>
        </div>
      )}
    </motion.li>
  )
}
