import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GITHUB_LOGIN_URL, getEvidenceCard, updateSearchable, type CandidateEvidence } from '../api'
import { useRequireCandidate } from '../hooks/useRequireCandidate'
import EvidenceCardList from '../components/EvidenceCardList'

// The authenticated landing experience for a returning Candidate (CONTEXT.md
// round 10) — replaces the old behavior of dropping straight into /claim.
// Reads the same latest-per-skill data /evidence-card/{candidateId} already
// serves publicly; no new backend read endpoint.
export default function Dashboard() {
  const { candidate, loading: authLoading } = useRequireCandidate()
  const candidateId = candidate?.candidate_id ?? null

  const [evidence, setEvidence] = useState<CandidateEvidence | null>(null)
  const [cardsLoading, setCardsLoading] = useState(true)
  const [searchable, setSearchable] = useState(false)
  const [toggling, setToggling] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!candidateId) return
    let cancelled = false
    getEvidenceCard(candidateId).then((data) => {
      if (cancelled) return
      setEvidence(data)
      setSearchable(data.searchable)
      setCardsLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [candidateId])

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
  const connectAccountBannerClassName = `mb-4 rounded-lg border p-3 text-sm ${
    candidate.needs_reconnect
      ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300'
      : 'border-neutral-200 text-neutral-500 dark:border-neutral-800'
  }`

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      <div className="w-full">
        <h1 className="font-wordmark mb-1 text-3xl">Your Evidence Cards</h1>
        <p className="mb-6 text-sm text-neutral-500">
          Signed in as <span className="font-mono">{candidate.github_login}</span>
        </p>

        <div className={connectAccountBannerClassName}>
          {candidate.needs_reconnect && (
            <p className="mb-2 font-medium">Your GitHub access was revoked, so this data may be stale.</p>
          )}
          <a
            href={GITHUB_LOGIN_URL}
            className="inline-block rounded-full border border-neutral-400 px-4 py-1.5 font-medium text-neutral-900 dark:border-neutral-600 dark:text-white"
          >
            Connect GitHub Account
          </a>
          <p className="mt-2 text-xs">
            Use this to reconnect if your access was revoked, or to connect a different GitHub account instead. To
            switch accounts, make sure you're already signed into that other account on github.com in this browser
            first — GitHub doesn't let this app show an account picker.
          </p>
        </div>

        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-neutral-200 p-4 text-left dark:border-neutral-800">
          <div className="flex items-center justify-between gap-3">
            <a href={publicCardPath} className="truncate font-mono text-sm underline underline-offset-2 hover:opacity-70">
              {publicCardPath}
            </a>
            <button
              type="button"
              onClick={handleCopyLink}
              className="shrink-0 rounded-full border border-neutral-300 px-3 py-1 text-sm dark:border-neutral-700"
            >
              {copied ? 'Copied!' : 'Copy link'}
            </button>
          </div>

          <label className="flex items-center justify-between gap-3 text-sm">
            Let recruiters find me in search
            <input
              type="checkbox"
              checked={searchable}
              disabled={toggling}
              onChange={handleToggleSearchable}
              className="h-4 w-4"
            />
          </label>
        </div>

        <EvidenceCardList cards={evidence?.cards ?? []} candidateId={candidate.candidate_id} />

        <Link
          to="/claim"
          className="mt-6 inline-block rounded-full bg-neutral-900 px-6 py-3 font-medium text-white dark:bg-white dark:text-neutral-900"
        >
          Claim more skills
        </Link>
      </div>
    </main>
  )
}
