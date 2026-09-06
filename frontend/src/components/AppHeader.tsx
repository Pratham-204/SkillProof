import { Link } from 'react-router-dom'

// Rendered once, outside <Routes>, on every page (App.tsx) — deliberately
// takes no props and reads no session state, so it can never become an
// owner-only affordance. PublicEvidenceCard's page content stays exactly as
// session-blind as before; this header is identical above it regardless of
// who's viewing.
export default function AppHeader() {
  return (
    <header className="mx-auto w-full max-w-5xl px-6 py-4">
      <Link to="/" className="font-wordmark flex items-center gap-2 text-lg">
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="8.5" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M6.5 10.3l2.3 2.3 4.7-5"
            stroke="var(--color-accent)"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        SkillProof
      </Link>
    </header>
  )
}
