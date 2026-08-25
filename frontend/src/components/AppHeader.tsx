import { Link } from 'react-router-dom'

// Rendered once, outside <Routes>, on every page (App.tsx) — deliberately
// takes no props and reads no session state, so it can never become an
// owner-only affordance. PublicEvidenceCard's page content stays exactly as
// session-blind as before; this header is identical above it regardless of
// who's viewing.
export default function AppHeader() {
  return (
    <header className="mx-auto w-full max-w-5xl px-6 py-4">
      <Link to="/" className="font-wordmark text-lg">
        SkillProof
      </Link>
    </header>
  )
}
