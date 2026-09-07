import { motion, useReducedMotion } from 'framer-motion'
import { useId, useState } from 'react'
import { explainSkill, type EvidenceCard } from '../api'
import {
  evidenceBadgeClassName,
  evidenceBadgeLabel,
  evidenceCardClassName,
  evidenceTypeSummary,
  isWeakEvidence,
} from '../lib/evidence'
import ScoreCounter from './ScoreCounter'
import StatusPanel from './system/StatusPanel'
import RankBadge from './system/RankBadge'
import { RANK_THEME, scoreToRank, type RankTheme } from './system/rank'

const cardVariants = {
  hidden: { opacity: 0, y: 16, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1 },
}

// Same start/end state so the mount "animation" is a visual no-op for
// prefers-reduced-motion users, without needing an app-wide <MotionConfig>.
const reducedMotionCardVariants = {
  hidden: { opacity: 1, y: 0, scale: 1 },
  visible: { opacity: 1, y: 0, scale: 1 },
}

// `ink` routes through the real --color-danger token instead of retyping its
// hex value; keeps this file's one failed-card literal from drifting further.
const DANGER_THEME: RankTheme = { ink: 'var(--color-danger)', glow: 'rgba(255,77,106,.3)' }

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
  const prefersReducedMotion = useReducedMotion()
  const variants = prefersReducedMotion ? reducedMotionCardVariants : cardVariants
  const detailsId = useId()

  if (card.status === 'failed') {
    return (
      <motion.li variants={variants} className="list-none">
        <StatusPanel theme={DANGER_THEME} className="text-left">
          <div className="p-4">
            <p className="font-display text-lg font-semibold text-danger-ink">{card.skill}</p>
            <p className="mt-1 text-sm text-danger-ink/80">{card.error ?? 'Verification failed.'}</p>
          </div>
        </StatusPanel>
      </motion.li>
    )
  }

  const isWeak = isWeakEvidence(card.evidence_type)
  const rank = scoreToRank(card.confidence_score, card.evidence_type)
  const rankTheme = RANK_THEME[rank]

  // A real explanation is fetched once per mount and held in this tile's own
  // state — re-expanding never re-fetches on top of it. A fallback explanation
  // (cached or freshly returned) is retried on every re-expand instead, mirroring
  // the backend's own "retried transparently on the next call" cache policy
  // (routers/explain.py) — otherwise a card that cached a fallback before the
  // LLM came back up would show stale template text forever, since `explanation`
  // is never null once the backend has cached anything at all.
  function fetchExplanation() {
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

  function handleToggle() {
    const opening = !expanded
    setExpanded(opening)
    if (opening && (explanation === null || isFallback) && !explaining) {
      fetchExplanation()
    }
  }

  return (
    <motion.li variants={variants} className="list-none">
      <StatusPanel theme={rankTheme} className={evidenceCardClassName(isWeak)}>
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={expanded}
          aria-controls={detailsId}
          className="focus-visible:outline-accent flex w-full items-start justify-between gap-3 text-left transition-[filter] duration-150 hover:brightness-110 focus-visible:brightness-110 active:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span className="flex min-w-0 items-center gap-3">
            <RankBadge rank={rank} size="sm" />
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="break-words font-display text-lg font-semibold tracking-wide">{card.skill}</span>
              <span className={evidenceBadgeClassName(card.evidence_type)}>{evidenceBadgeLabel(card.evidence_type)}</span>
            </span>
          </span>
          <ScoreCounter score={card.confidence_score} className="text-xl" />
        </button>
        <p className="mt-1 text-xs text-ink-dim">
          {evidenceTypeSummary(card.evidence_type, card.source_commits.length)}
        </p>

        {expanded && (
          <div id={detailsId} className="mt-3 flex flex-col gap-3 border-t border-edge pt-3">
            {card.source_commits.length > 0 && (
              <ul className="flex flex-col gap-1">
                {card.source_commits.map((ref) =>
                  ref.private ? (
                    <li key={`${ref.kind}-${ref.ref}`} className="font-mono text-xs text-ink-dim">
                      {ref.kind === 'commit' ? 'Commit' : 'PR comment'} in {ref.repo}
                    </li>
                  ) : (
                    <li key={`${ref.kind}-${ref.ref}`} className="font-mono text-xs">
                      <a
                        href={ref.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent-ink focus-visible:outline-accent underline underline-offset-2 transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                      >
                        {ref.kind === 'commit' ? 'commit' : 'PR comment'} {ref.ref.slice(0, 7)}
                      </a>
                      <span className="ml-2 text-ink-dim">{ref.repo}</span>
                    </li>
                  ),
                )}
              </ul>
            )}

            <div className="text-sm">
              {explaining && <p className="italic text-ink-dim">Generating explanation…</p>}
              {explainError && (
                <p className="text-danger-ink">
                  {explainError}{' '}
                  <button
                    type="button"
                    onClick={fetchExplanation}
                    className="focus-visible:outline-accent underline underline-offset-2 transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  >
                    Retry
                  </button>
                </p>
              )}
              {explanation && (
                <p>
                  {explanation}
                  {isFallback && (
                    <span className="ml-2 rounded-full border border-edge bg-surface-2 px-2 py-0.5 font-mono text-[0.65rem] uppercase tracking-wide text-ink-dim">
                      template fallback
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
        )}
      </StatusPanel>
    </motion.li>
  )
}
