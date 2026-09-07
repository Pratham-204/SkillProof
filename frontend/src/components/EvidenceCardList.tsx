import { motion } from 'framer-motion'
import { MAX_CLAIMED_SKILLS, type EvidenceCard } from '../api'
import EvidenceCardTile from './EvidenceCardTile'
import StatusPanel from './system/StatusPanel'

const CARD_STAGGER_SECONDS = 0.32

// The staggered materialize is only meant to feel orchestrated for a single
// verification run (at most MAX_CLAIMED_SKILLS cards) — ScanReveal is the one
// place that deliberate reveal earns its keep. Dashboard and the public
// Evidence Card page reuse this same list to show an already-complete history
// that "Claim more skills" can grow well past that cap across repeated
// visits, so beyond it the per-card delay shrinks to keep the *total* reveal
// time bounded instead of the last tile sitting invisible for seconds on a
// page that isn't a live reveal at all.
const MAX_TOTAL_STAGGER_SECONDS = MAX_CLAIMED_SKILLS * CARD_STAGGER_SECONDS

function getListVariants(cardCount: number) {
  const staggerChildren =
    cardCount > MAX_CLAIMED_SKILLS ? MAX_TOTAL_STAGGER_SECONDS / cardCount : CARD_STAGGER_SECONDS
  return {
    hidden: {},
    visible: { transition: { staggerChildren } },
  }
}

interface EvidenceCardListProps {
  cards: EvidenceCard[]
  candidateId: string
  /** Shown instead of the list when `cards` is empty — e.g. a brand-new candidate who hasn't claimed a skill yet. */
  emptyMessage?: string
}

// Shared between the live scan/reveal view (ticket 05) and the public,
// already-complete Evidence Card page (ticket 07) — both stagger the same
// tiles in via Framer Motion, just against a live vs. a pre-fetched list.
export default function EvidenceCardList({ cards, candidateId, emptyMessage = 'No Evidence Cards yet.' }: EvidenceCardListProps) {
  if (cards.length === 0) {
    return (
      <StatusPanel size="sm" className="p-6 text-center">
        <p className="text-ink-dim text-sm">{emptyMessage}</p>
      </StatusPanel>
    )
  }

  return (
    <motion.ul
      initial="hidden"
      animate="visible"
      variants={getListVariants(cards.length)}
      className="flex w-full flex-col gap-3"
    >
      {cards.map((card) => (
        <EvidenceCardTile key={card.skill} card={card} candidateId={candidateId} />
      ))}
    </motion.ul>
  )
}
