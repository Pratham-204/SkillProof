import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GITHUB_LOGIN_URL, getEvidenceCard, updateSearchable, type CandidateEvidence } from '../api'
import { useRequireCandidate } from '../hooks/useRequireCandidate'
import EvidenceCardList from '../components/EvidenceCardList'
import StatusPanel from '../components/system/StatusPanel'

// The authenticated landing experience for a returning Candidate (CONTEXT.md
// round 10) — replaces the old behavior of dropping straight into /claim.
// Reads the same latest-per-skill data /evidence-card/{candidateId} already
// serves publicly; no new backend read endpoint.
export default function Dashboard() {
  const { candidate, loading: authLoading } = useRequireCandidate()
  const candidateId = candidate?.candidate_id ?? null

  const [evidence, setEvidence] = useState<CandidateEvidence | null>(null)
  const [cardsLoading, setCardsLoading] = useState(true)
  const [cardsError, setCardsError] = useState(false)
  const [searchable, setSearchable] = useState(false)
  const [toggling, setToggling] = useState(false)
  const [copied, setCopied] = useState(false)
  // Bumped by the retry button below to re-run the effect after a failed fetch.
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    if (!candidateId) return
    let cancelled = false
    setCardsLoading(true)
    setCardsError(false)
    getEvidenceCard(candidateId)
      .then((data) => {
        if (cancelled) return
        setEvidence(data)
        setSearchable(data.searchable)
        setCardsLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setCardsError(true)
        setCardsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [candidateId, retryToken])

  async function handleToggleSearchable() {
    const next = !searchable
    setSearchable(next) // optimistic: flips immediately, rolled back below on failure
    setToggling(true)
    try {
      const updated = await updateSearchable(next)
      setSearchable(updated.searchable)
    } catch {
      setSearchable(!next)
    } finally {
      setToggling(false)
    }
  }

  if (authLoading || cardsLoading || !candidate) return null

  // Only reachable once `candidate` is guaranteed non-null (the guard above),
  // so these read straight off it instead of re-deriving/re-checking `candidateId`.
  const publicCardPath = `/c/${candidate.candidate_id}`

  function handleCopyLink() {
    navigator.clipboard.writeText(`${window.location.origin}${publicCardPath}`).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  // One button, not two (ADR-0014): reconnecting a revoked token and connecting a
  // different GitHub account are the same /auth/github/login redirect underneath, so
  // this single block covers both instead of a separate needs_reconnect-only banner.
  const reconnectTheme = candidate.needs_reconnect
    ? { ink: '#ff4d6a', glow: 'rgba(255,77,106,.28)' }
    : { ink: '#1c2b45', glow: 'transparent' }

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      <div className="w-full">
        <h1 className="font-display mb-1 text-3xl font-semibold tracking-wide">Your Evidence Cards</h1>
        <p className="text-ink-dim mb-6 text-sm">
          Signed in as <span className="font-mono">{candidate.github_login}</span>
        </p>

        <StatusPanel theme={reconnectTheme} size="sm" className="mb-4 p-3 text-left text-sm">
          {candidate.needs_reconnect && (
            <p className="text-danger-ink mb-2 font-medium">Your GitHub access was revoked, so this data may be stale.</p>
          )}
          <a
            href={GITHUB_LOGIN_URL}
            className="border-accent/50 text-accent-ink hover:bg-accent-soft focus-visible:outline-accent inline-block rounded-full border px-4 py-1.5 font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            Connect GitHub Account
          </a>
          <p className="text-ink-dim mt-2 text-xs">
            Use this to reconnect if your access was revoked, or to connect a different GitHub account instead. To
            switch accounts, make sure you're already signed into that other account on github.com in this browser
            first — GitHub doesn't let this app show an account picker.
          </p>
        </StatusPanel>

        <StatusPanel size="sm" className="mb-6 flex flex-col gap-3 p-4 text-left">
          <div className="flex items-center justify-between gap-3">
            <a
              href={publicCardPath}
              className="text-accent-ink focus-visible:outline-accent min-w-0 flex-1 truncate font-mono text-sm underline underline-offset-2 transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              {publicCardPath}
            </a>
            <button
              type="button"
              onClick={handleCopyLink}
              aria-live="polite"
              className="border-edge hover:border-accent hover:text-accent-ink focus-visible:outline-accent shrink-0 rounded-full border px-3 py-1 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              {copied ? 'Copied!' : 'Copy link'}
            </button>
          </div>

          <label className="flex items-center justify-between gap-3 py-2 text-sm">
            Let recruiters find me in search
            <input
              type="checkbox"
              checked={searchable}
              disabled={toggling}
              onChange={handleToggleSearchable}
              className="accent-accent h-4 w-4"
            />
          </label>
        </StatusPanel>

        {cardsError ? (
          <StatusPanel size="sm" className="mb-6 flex flex-col items-center gap-3 p-4 text-center text-sm">
            <p className="text-danger-ink">Couldn't load your evidence cards.</p>
            <button
              type="button"
              onClick={() => setRetryToken((t) => t + 1)}
              className="border-edge hover:border-accent hover:text-accent-ink focus-visible:outline-accent rounded-full border px-4 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Retry
            </button>
          </StatusPanel>
        ) : (
          <EvidenceCardList cards={evidence?.cards ?? []} candidateId={candidate.candidate_id} />
        )}

        <Link
          to="/claim"
          className="bg-accent text-on-accent mt-6 inline-block rounded-full px-6 py-3 font-medium shadow-[0_0_24px_-6px_var(--color-accent)] transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          Claim more skills
        </Link>
      </div>
    </main>
  )
}
