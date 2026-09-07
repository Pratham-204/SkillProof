import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RateLimitedError, listSkills, searchCandidates, type SearchResult, type SkillTag } from '../api'
import ScoreCounter from '../components/ScoreCounter'
import SkillPicker from '../components/SkillPicker'
import StatusPanel from '../components/system/StatusPanel'
import RankBadge from '../components/system/RankBadge'
import { RANK_THEME, scoreToRank } from '../components/system/rank'
import {
  evidenceBadgeClassName,
  evidenceBadgeLabel,
  evidenceCardClassName,
  evidenceTypeSummary,
  isWeakEvidence,
} from '../lib/evidence'

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
        <p className="text-accent mb-1 font-mono text-xs tracking-[0.3em]">[ GUILD REQUEST BOARD ]</p>
        <h1 className="font-display text-3xl font-semibold tracking-wide">Find candidates</h1>
        <p className="text-ink-dim mt-1">Search by verified skills — results must match every skill selected.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-4">
        {/* Same autocomplete source as the claim-skills flow (ticket 04). AND
            semantics across selections (ADR-0007), capped at 8 like /verify's
            claims-per-call cap. */}
        <SkillPicker skills={skills} selected={selectedSkills} onChange={setSelectedSkills} max={MAX_SEARCH_SKILLS} />

        <button
          type="submit"
          disabled={selectedSkills.length === 0 || status === 'loading'}
          className="bg-accent text-on-accent w-full rounded-full px-6 py-3 font-medium shadow-[0_0_24px_-6px_var(--color-accent)] transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          {status === 'loading' ? 'Searching…' : 'Search'}
        </button>
      </form>

      {status === 'rate-limited' && (
        <StatusPanel theme={{ ink: '#ffd76a', glow: 'rgba(255,215,106,.3)' }} size="sm" className="w-full p-3 text-center text-sm">
          <p className="text-gold">Too many searches — try again shortly.</p>
        </StatusPanel>
      )}
      {status === 'error' && (
        <StatusPanel theme={{ ink: '#ff4d6a', glow: 'rgba(255,77,106,.28)' }} size="sm" className="w-full p-3 text-center text-sm">
          <p className="text-danger-ink">Something went wrong searching. Try again.</p>
        </StatusPanel>
      )}

      {status === 'ready' && (
        <ul className="flex w-full flex-col gap-4">
          {results.length === 0 && <p className="text-ink-dim text-center">No matching candidates.</p>}
          {results.map((r) => {
            const overallRank = scoreToRank(r.average_score, 'verified')
            return (
              <StatusPanel key={r.candidate_id} as="li" theme={RANK_THEME[overallRank]} className="p-4 text-left">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 flex-1 items-center gap-3">
                    <RankBadge rank={overallRank} size="sm" title={`Average rank ${overallRank}`} />
                    <a
                      href={r.github_profile_url}
                      target="_blank"
                      rel="noreferrer"
                      className="focus-visible:outline-accent min-w-0 truncate font-medium underline underline-offset-2 transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                    >
                      {r.github_login}
                    </a>
                  </span>
                  <ScoreCounter score={r.average_score} className="shrink-0 text-lg" />
                </div>

                {/* Each matched skill gets its own lit-vs-dim treatment — the
                    same evidence_type visual language as EvidenceCardTile —
                    so a verified skill within the stack can't be mistaken for
                    a declared_only one just because the overall average is
                    decent. */}
                <ul className="mt-3 flex flex-col gap-2">
                  {r.matches.map((m) => {
                    const isWeak = isWeakEvidence(m.evidence_type)
                    const matchRank = scoreToRank(m.confidence_score, m.evidence_type)
                    return (
                      <StatusPanel key={m.skill} as="li" size="sm" theme={RANK_THEME[matchRank]} className={evidenceCardClassName(isWeak)}>
                        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <RankBadge rank={matchRank} size="sm" />
                            <span className="font-display font-semibold break-words">{m.skill}</span>
                            <span className={evidenceBadgeClassName(m.evidence_type)}>
                              {evidenceBadgeLabel(m.evidence_type)}
                            </span>
                          </span>
                          <ScoreCounter score={m.confidence_score} className="shrink-0 text-sm" />
                        </div>
                        <p className="text-ink-dim mt-1 text-xs">{evidenceTypeSummary(m.evidence_type)}</p>
                      </StatusPanel>
                    )
                  })}
                </ul>

                <div className="text-ink-dim mt-3 flex items-center justify-end text-xs">
                  <Link
                    to={`/c/${r.candidate_id}`}
                    className="text-accent-ink focus-visible:outline-accent underline underline-offset-2 transition hover:opacity-70 active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  >
                    View Evidence Card
                  </Link>
                </div>
              </StatusPanel>
            )
          })}
        </ul>
      )}
    </main>
  )
}
