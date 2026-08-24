import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RateLimitedError, listSkills, searchCandidates, type SearchResult, type SkillTag } from '../api'
import ScoreCounter from '../components/ScoreCounter'
import SkillPicker from '../components/SkillPicker'
import { evidenceCardClassName, evidenceTypeSummary, isWeakEvidence } from '../lib/evidence'

type Status = 'idle' | 'loading' | 'ready' | 'rate-limited' | 'error'

const MAX_SEARCH_SKILLS = 8

// Fully unauthenticated per ADR-0002 — no login/account affordance anywhere on
// this page, matching the backend having no Recruiter auth model at all.
export default function RecruiterSearch() {
  const [skills, setSkills] = useState<SkillTag[]>([])
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const [results, setResults] = useState<SearchResult[]>([])
  const [status, setStatus] = useState<Status>('idle')

  useEffect(() => {
    listSkills().then(setSkills)
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (selectedSkills.length === 0 || status === 'loading') return
    setStatus('loading')
    try {
      // Rendered in exactly the order the API returns — no client-side re-sort.
      const found = await searchCandidates(selectedSkills)
      setResults(found)
      setStatus('ready')
    } catch (err) {
      setStatus(err instanceof RateLimitedError ? 'rate-limited' : 'error')
    }
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center gap-8 px-6 py-16">
      <div className="text-center">
        <h1 className="font-wordmark text-3xl">Find candidates</h1>
        <p className="mt-1 text-neutral-500">
          Search by verified skills — results must match every skill selected.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-4">
        {/* Same autocomplete source as the claim-skills flow (ticket 04). AND
            semantics across selections (ADR-0007), capped at 8 like /verify's
            claims-per-call cap. */}
        <SkillPicker skills={skills} selected={selectedSkills} onChange={setSelectedSkills} max={MAX_SEARCH_SKILLS} />

        <button
          type="submit"
          disabled={selectedSkills.length === 0 || status === 'loading'}
          className="w-full rounded-full bg-neutral-900 px-6 py-3 font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-neutral-900"
        >
          {status === 'loading' ? 'Searching…' : 'Search'}
        </button>
      </form>

      {status === 'rate-limited' && (
        <p className="text-sm text-amber-700 dark:text-amber-400">Too many searches — try again shortly.</p>
      )}
      {status === 'error' && (
        <p className="text-sm text-red-600 dark:text-red-400">Something went wrong searching. Try again.</p>
      )}

      {status === 'ready' && (
        <ul className="flex w-full flex-col gap-4">
          {results.length === 0 && <p className="text-center text-neutral-500">No matching candidates.</p>}
          {results.map((r) => (
            <li
              key={r.candidate_id}
              className="rounded-xl border border-neutral-200 bg-white p-4 text-left shadow-sm dark:border-neutral-800 dark:bg-neutral-900"
            >
              <div className="flex items-center justify-between gap-3">
                <a
                  href={r.github_profile_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium underline underline-offset-2"
                >
                  {r.github_login}
                </a>
                <ScoreCounter score={r.average_score} className="text-lg" />
              </div>

              {/* Each matched skill gets its own solid-vs-dashed treatment —
                  the same evidence_type visual language as EvidenceCardTile —
                  so a verified skill within the stack can't be mistaken for a
                  declared_only one just because the overall average is decent. */}
              <ul className="mt-2 flex flex-col gap-2">
                {r.matches.map((m) => {
                  const isWeak = isWeakEvidence(m.evidence_type)
                  return (
                    <li key={m.skill} className={evidenceCardClassName(isWeak)}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">{m.skill}</span>
                        <ScoreCounter score={m.confidence_score} className={`text-sm ${isWeak ? 'opacity-60' : ''}`} />
                      </div>
                      <p className={`mt-1 text-xs ${isWeak ? 'text-neutral-500' : 'text-neutral-600 dark:text-neutral-400'}`}>
                        {evidenceTypeSummary(m.evidence_type)}
                      </p>
                    </li>
                  )
                })}
              </ul>

              <div className="mt-2 flex items-center justify-end text-xs text-neutral-500">
                <Link to={`/c/${r.candidate_id}`} className="underline underline-offset-2">
                  View Evidence Card
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
