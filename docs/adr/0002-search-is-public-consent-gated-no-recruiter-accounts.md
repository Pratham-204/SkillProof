# Evidence Cards and /search are public and unauthenticated, gated by Candidate consent instead of recruiter accounts

Recruiter authentication (signup, login, sessions, password reset) was considered and rejected for MVP: it costs 1-2 weeks, adds no differentiating capability, and adds friction to sharing demo links — while `/search` itself is a stateless, sorted database query with no per-recruiter data to protect. Instead, `/evidence-card/{candidate_id}` and `/search` stay fully public and unauthenticated. Search is gated by (a) a per-Candidate `searchable` boolean, defaulting to `false`, that the Candidate opts into when generating their card, and (b) a 60-requests/minute-per-IP rate limit (slowapi) to blunt bulk scraping of the candidate index.

## Considered Options

Recruiter accounts with auth-gated search — rejected for MVP as disproportionate cost for no differentiating capability at this stage.

## Reversal trigger

Build recruiter accounts only when per-recruiter state is actually needed — saved searches, candidate shortlists, or usage-based billing. Search being stateless is what makes auth unnecessary today; the moment that stops being true, revisit this.
