import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { GITHUB_LOGIN_URL, getEvidenceCard, type EvidenceCard as EvidenceCardType } from '../api'
import { useRequireCandidate } from '../hooks/useRequireCandidate'
import EvidenceCardList from '../components/EvidenceCardList'

type Phase = 'idle' | 'scanning' | 'revealing' | 'complete'

// Floored, not fabricated: a fast verification (few small repos) still holds
// the scanning phase open this long so the reveal never collapses into an
// instant, anticlimactic flash — but everything shown during it is real.
const MIN_SCAN_MS = 1500

export default function ScanReveal() {
  const { candidate } = useRequireCandidate()
  const [phase, setPhase] = useState<Phase>('idle')
  const candidateId = candidate?.candidate_id ?? null
  const [scannedRepos, setScannedRepos] = useState<string[]>([])
  const [cards, setCards] = useState<EvidenceCardType[]>([])
  // The skills this run is verifying, derived from the Candidate's own
  // Evidence Cards (status "processing" is stamped synchronously by
  // start_verification before this page can even mount) rather than router
  // `location.state`, which only survives one specific in-app navigation and
  // is silently empty on refresh, back/forward, or a direct visit. `null`
  // means "not yet fetched" and holds off the completion check below.
  const [expectedSkills, setExpectedSkills] = useState<string[] | null>(null)
  // Flips true once the "done" handler's own backfill fetch (below) has
  // resolved — the authoritative post-run read that closes the window where
  // `expectedSkills` undercounted.
  const [doneCardsSettled, setDoneCardsSettled] = useState(false)

  const scanFloorPassed = useRef(false)
  const verificationDone = useRef(false)
  const revealedSkills = useRef<Set<string>>(new Set())

  // Starts the phase machine once identity resolves (`phase === 'idle'` keeps
  // rendering suppressed below until then, same as the old loading gate).
  useEffect(() => {
    if (candidate) setPhase('scanning')
  }, [candidate])

  function tryEnterRevealing() {
    if (scanFloorPassed.current && verificationDone.current) {
      setPhase((p) => (p === 'scanning' ? 'revealing' : p))
    }
  }

  useEffect(() => {
    if (!candidateId) return
    let cancelled = false
    getEvidenceCard(candidateId).then((evidence) => {
      if (cancelled) return
      setExpectedSkills(evidence.cards.filter((c) => c.status === 'processing').map((c) => c.skill))
    })
    return () => {
      cancelled = true
    }
  }, [candidateId])

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
      // its (failed) card still shows up once verification is over. This
      // fetch is also the last word on `expectedSkills` potentially having
      // undercounted (a skill can finish between that snapshot firing and
      // resolving, or its "reveal" event can be missed entirely — the
      // progress bus doesn't replay events published before this page
      // subscribed) — so completion below waits on it too.
      getEvidenceCard(candidateId)
        .then((evidence) => {
          setCards((prev) => {
            const known = new Set(prev.map((c) => c.skill))
            // Sorted alphabetically here rather than trusting this fetch's own
            // order (which ranks by score, for the Dashboard/public card) — a
            // skill that fails before ever revealing (e.g. _fail_card, which
            // never publishes a "reveal" event) only ever arrives through this
            // backfill, so its position shouldn't depend on an ordering meant
            // for a different view.
            const missing = evidence.cards
              .filter((c) => !known.has(c.skill))
              .sort((a, b) => a.skill.localeCompare(b.skill))
            return missing.length ? [...prev, ...missing] : prev
          })
        })
        .finally(() => setDoneCardsSettled(true))
      source.close()
    })

    return () => source.close()
  }, [candidateId])

  // Once the run is done and every expected card has arrived, we're complete.
  // Waits on expectedSkills to resolve before deciding anything (it starts
  // `null`), then falls back to "done + at least one card" if it came back
  // empty (e.g. verification finished before this page's fetch landed)
  // rather than an exact count that could never match. Also waits on
  // doneCardsSettled so a count that happened to match early can't flip this
  // to `complete` before the "done" handler's own authoritative fetch lands.
  useEffect(() => {
    if (phase !== 'revealing' || !verificationDone.current || !doneCardsSettled) return
    if (expectedSkills === null) return
    if (expectedSkills.length > 0 && cards.length < expectedSkills.length) return
    if (cards.length === 0) return
    setPhase('complete')
  }, [phase, cards, expectedSkills, doneCardsSettled])

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
