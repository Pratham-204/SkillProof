import { motion } from 'framer-motion'
import type { EvidenceCard } from '../api'
import EvidenceCardTile from './EvidenceCardTile'

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.32 } },
}

interface EvidenceCardListProps {
  cards: EvidenceCard[]
  candidateId: string
}

// Shared between the live scan/reveal view (ticket 05) and the public,
// already-complete Evidence Card page (ticket 07) — both stagger the same
// tiles in via Framer Motion, just against a live vs. a pre-fetched list.
export default function EvidenceCardList({ cards, candidateId }: EvidenceCardListProps) {
  return (
    <motion.ul initial="hidden" animate="visible" variants={listVariants} className="flex w-full flex-col gap-3">
      {cards.map((card) => (
        <EvidenceCardTile key={card.skill} card={card} candidateId={candidateId} />
      ))}
    </motion.ul>
  )
}
