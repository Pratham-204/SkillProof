import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { GITHUB_LOGIN_URL, getEvidenceCard, getMe, type Candidate, type EvidenceCard as EvidenceCardType } from '../api'
import EvidenceCardList from '../components/EvidenceCardList'

type Phase = 'idle' | 'scanning' | 'revealing' | 'complete'

// Floored, not fabricated: a fast verification (few small repos) still holds
// the scanning phase open this long so the reveal never collapses into an
// instant, anticlimactic flash — but everything shown during it is real.
const MIN_SCAN_MS = 1500

export default function ScanReveal() {
  const location = useLocation()
  const navigate = useNavigate()
  const claimedSkills = (location.state as { skills?: string[] } | null)?.skills ?? []

  const [phase, setPhase] = useState<Phase>('idle')
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const candidateId = candidate?.candidate_id ?? null
  const [scannedRepos, setScannedRepos] = useState<string[]>([])
  const [cards, setCards] = useState<EvidenceCardType[]>([])

  const scanFloorPassed = useRef(false)
  const verificationDone = useRef(false)
  const revealedSkills = useRef<Set<string>>(new Set())

  // Resolve identity once, then start the phase machine.
  useEffect(() => {
    let cancelled = false
    getMe().then((me) => {
      if (cancelled) return
      if (!me) {
        navigate('/', { replace: true })
        return
      }
      setCandidate(me)
      setPhase('scanning')
    })
    return () => {
      cancelled = true
    }
  }, [navigate])

  function tryEnterRevealing() {
    if (scanFloorPassed.current && verificationDone.current) {
      setPhase((p) => (p === 'scanning' ? 'revealing' : p))
    }
  }

  // The scan floor: a plain timer, independent of how fast real events arrive.
  useEffect(() => {
    if (phase !== 'scanning') return
    scanFloorPassed.current = false
    const timer = setTimeout(() => {
      scanFloorPassed.current = true
      tryEnterRevealing()
    }, MIN_SCAN_MS)
    return () => clearTimeout(timer)
  }, [phase])

  // The live SSE connection — real scan/reveal/done events (ticket 03), never
  // simulated. Pulls the freshly-committed card on each reveal event rather
  // than waiting for "done" to fetch everything at once, so cards actually
  // arrive incrementally as backend work finishes.
  useEffect(() => {
    if (!candidateId) return

    const source = new EventSource(`/verify/${candidateId}/stream`, { withCredentials: true })

    source.addEventListener('scan', (e) => {
      const repo = (e as MessageEvent).data
      setScannedRepos((prev) => (prev.includes(repo) ? prev : [...prev, repo]))
    })

    source.addEventListener('reveal', (e) => {
      const skill = (e as MessageEvent).data
      if (revealedSkills.current.has(skill)) return
      revealedSkills.current.add(skill)
      getEvidenceCard(candidateId).then((evidence) => {
        const card = evidence.cards.find((c) => c.skill === skill)
        if (card) setCards((prev) => (prev.some((c) => c.skill === skill) ? prev : [...prev, card]))
      })
    })

    source.addEventListener('done', () => {
      verificationDone.current = true
      tryEnterRevealing()
      // A skill can fail before ever producing a "reveal" event — make sure
      // its (failed) card still shows up once verification is over.
      getEvidenceCard(candidateId).then((evidence) => {
        setCards((prev) => {
          const known = new Set(prev.map((c) => c.skill))
          const missing = evidence.cards.filter((c) => !known.has(c.skill))
          return missing.length ? [...prev, ...missing] : prev
        })
      })
      source.close()
    })

    return () => source.close()
  }, [candidateId])

  // Once the run is done and every claimed card has arrived, we're complete.
  // Falls back to "done + at least one card" if claimedSkills is unknown
  // (e.g. this page was reached directly rather than via the claim form,
  // losing router state) rather than an exact count that could never match.
  useEffect(() => {
    if (phase !== 'revealing' || !verificationDone.current) return
    if (claimedSkills.length > 0 && cards.length < claimedSkills.length) return
    if (cards.length === 0) return
    setPhase('complete')
  }, [phase, cards, claimedSkills.length])

  if (phase === 'idle') return null

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      {phase === 'scanning' && (
        <div className="flex flex-col items-center gap-3">
          <h1 className="font-wordmark text-3xl">Scanning your repos…</h1>
          <ul className="font-mono text-sm text-neutral-500">
            {scannedRepos.map((repo) => (
              <motion.li key={repo} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                {repo}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {(phase === 'revealing' || phase === 'complete') && (
        <div className="w-full">
          <h1 className="font-wordmark mb-6 text-3xl">
            {phase === 'complete' ? 'Your Evidence Cards' : 'Revealing…'}
          </h1>

          {phase === 'complete' && candidate?.needs_reconnect && (
            <p className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              Your GitHub access was revoked, so this run used stale data.{' '}
              <a href={GITHUB_LOGIN_URL} className="font-medium underline underline-offset-2">
                Reconnect GitHub
              </a>{' '}
              to re-verify with fresh access.
            </p>
          )}

          <EvidenceCardList cards={cards} candidateId={candidateId ?? ''} />
        </div>
      )}
    </main>
  )
}
