import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RateLimitedError, listSkills, searchCandidates, type SearchResult, type SkillTag } from '../api'
import SkillPicker from '../components/SkillPicker'

type Status = 'idle' | 'loading' | 'ready' | 'rate-limited' | 'error'

// Fully unauthenticated per ADR-0002 — no login/account affordance anywhere on
// this page, matching the backend having no Recruiter auth model at all.
export default function RecruiterSearch() {
  const [skills, setSkills] = useState<SkillTag[]>([])
  const [selectedSkill, setSelectedSkill] = useState<string[]>([])
  const [minScore, setMinScore] = useState(0)
  const [results, setResults] = useState<SearchResult[]>([])
  const [status, setStatus] = useState<Status>('idle')

  useEffect(() => {
    listSkills().then(setSkills)
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const skill = selectedSkill[0]
    if (!skill || status === 'loading') return
    setStatus('loading')
    try {
      // Rendered in exactly the order the API returns — no client-side re-sort.
      const found = await searchCandidates(skill, minScore)
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
        <p className="mt-1 text-neutral-500">Search by verified skill and minimum confidence.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-4">
        {/* Same autocomplete source as the claim-skills flow (ticket 04), capped
            at 1 selection since search is single-skill. */}
        <SkillPicker skills={skills} selected={selectedSkill} onChange={setSelectedSkill} max={1} />

        <label className="flex w-full flex-col gap-1 text-left text-sm text-neutral-600 dark:text-neutral-400">
          Minimum confidence
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="rounded-lg border border-neutral-300 px-4 py-2 outline-none focus:border-neutral-900 dark:border-neutral-700 dark:bg-transparent dark:focus:border-white"
          />
        </label>

        <button
          type="submit"
          disabled={selectedSkill.length === 0 || status === 'loading'}
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
        <ul className="flex w-full flex-col gap-3">
          {results.length === 0 && <p className="text-center text-neutral-500">No matching candidates.</p>}
          {results.map((r) => {
            const isWeak = r.evidence_type !== 'verified'
            return (
              <li
                key={r.candidate_id}
                className={`rounded-xl border p-4 text-left ${
                  isWeak
                    ? 'border-dashed border-neutral-300 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900/40'
                    : 'border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900'
                }`}
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
                  <span className={`font-mono text-lg tabular-nums ${isWeak ? 'opacity-60' : ''}`}>
                    {Math.round(r.confidence_score * 100)}
                    <span className="text-[0.6em] opacity-60">%</span>
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-xs text-neutral-500">
                  <span>
                    {r.evidence_type === 'declared_only' ? 'Declared only — never committed to' : r.evidence_type}
                  </span>
                  <Link to={`/c/${r.candidate_id}`} className="underline underline-offset-2">
                    View Evidence Card
                  </Link>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </main>
  )
}
