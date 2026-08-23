import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getEvidenceCard, type CandidateEvidence } from '../api'
import EvidenceCardList from '../components/EvidenceCardList'

type Status = 'loading' | 'ready' | 'not-found'

// No SSE, no scanning phase — there's nothing in progress here. Enters the
// same staggered reveal ticket 05 uses, straight against the already-complete
// card list `/evidence-card/{candidateId}` returns. Deliberately session-blind:
// this route never checks getMe(), so a Candidate visiting their own public
// link sees exactly the same view a stranger would, with no owner-only actions.
export default function PublicEvidenceCard() {
  const { candidateId } = useParams<{ candidateId: string }>()
  const [evidence, setEvidence] = useState<CandidateEvidence | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    if (!candidateId) return
    let cancelled = false
    getEvidenceCard(candidateId)
      .then((data) => {
        if (cancelled) return
        setEvidence(data)
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setStatus('not-found')
      })
    return () => {
      cancelled = true
    }
  }, [candidateId])

  if (status === 'loading') return null

  if (status === 'not-found' || !evidence) {
    return (
      <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="font-wordmark text-3xl">Not found</h1>
        <p className="text-neutral-500">No Evidence Card exists for this candidate.</p>
      </main>
    )
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      <div className="w-full">
        <h1 className="font-wordmark mb-1 text-3xl">{evidence.github_login}</h1>
        <p className="mb-6 text-sm text-neutral-500">
          Verified against real GitHub activity — not a resume line.
        </p>
        <EvidenceCardList cards={evidence.cards} candidateId={evidence.candidate_id} />
      </div>
    </main>
  )
}
