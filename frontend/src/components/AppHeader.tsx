import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getMe, type Candidate } from '../api'

// Rendered once, outside <Routes>, on every page (App.tsx). The wordmark side
// is always session-blind. The identity chip on the right is the one
// deliberate exception: it's suppressed on `/c/:candidateId` specifically, so
// PublicEvidenceCard's invariant ("identical output regardless of
// viewer/session") holds exactly as before — everywhere else, a signed-in
// Candidate gets a quick way back to their own Dashboard instead of the
// header looking the same for them as for a stranger.
const PUBLIC_CARD_ROUTE = /^\/c\//

export default function AppHeader() {
  const { pathname } = useLocation()
  const isPublicCard = PUBLIC_CARD_ROUTE.test(pathname)
  const [candidate, setCandidate] = useState<Candidate | null>(null)

  useEffect(() => {
    if (isPublicCard) return
    let cancelled = false
    getMe().then((me) => {
      if (!cancelled) setCandidate(me)
    })
    return () => {
      cancelled = true
    }
  }, [isPublicCard])

  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">
      <Link
        to="/"
        className="font-display inline-flex items-center gap-2 text-lg font-semibold tracking-wide text-ink transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path
            d="M10 1.2 17.6 5.6v8.8L10 18.8 2.4 14.4V5.6Z"
            stroke="var(--color-accent)"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <path
            d="M6.6 10.2l2.3 2.3 4.6-4.9"
            stroke="var(--color-accent)"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        SkillProof
      </Link>

      {!isPublicCard && candidate && (
        <Link
          to="/dashboard"
          className="border-edge bg-surface text-ink-dim hover:border-accent hover:text-accent-ink focus-visible:outline-accent flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span className="bg-accent h-1.5 w-1.5 shrink-0 rounded-full" aria-hidden="true" />
          <span className="max-w-[16ch] truncate font-mono">{candidate.github_login}</span>
        </Link>
      )}
    </header>
  )
}
