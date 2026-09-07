import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GITHUB_LOGIN_URL, MAX_CLAIMED_SKILLS, listSkills, verify, type SkillTag } from '../api'
import { useRequireCandidate } from '../hooks/useRequireCandidate'
import SkillPicker from '../components/SkillPicker'
import StatusPanel from '../components/system/StatusPanel'
import SystemText from '../components/system/SystemText'

export default function ClaimSkills() {
  const navigate = useNavigate()
  const { candidate, loading: authLoading } = useRequireCandidate()
  const [skills, setSkills] = useState<SkillTag[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [searchable, setSearchable] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [skillsLoading, setSkillsLoading] = useState(true)
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    setSkillsLoading(true)
    setSkillsError(null)
    listSkills()
      .then((skillList) => {
        if (cancelled) return
        setSkills(skillList)
        setSkillsLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setSkillsError(err instanceof Error ? err.message : 'Could not load the skill list.')
        setSkillsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [retryToken])

  // Seed the checkbox from the candidate's current setting once it loads, so
  // claiming more skills doesn't silently opt an already-searchable candidate
  // back out just because this form's local state starts at `false`.
  useEffect(() => {
    if (candidate) setSearchable(candidate.searchable)
  }, [candidate])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (selected.length === 0 || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await verify(selected, searchable)
      navigate('/scan')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong starting verification.')
      setSubmitting(false)
    }
  }

  if (authLoading || skillsLoading) return null

  if (candidate?.needs_reconnect) {
    return (
      <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="font-display text-3xl font-semibold tracking-wide">Reconnect GitHub</h1>
        <p className="text-ink-dim">
          Your GitHub access has been revoked, so verification can't run until you reconnect.
        </p>
        <a
          href={GITHUB_LOGIN_URL}
          className="bg-accent text-on-accent rounded-full px-6 py-3 font-medium shadow-[0_0_24px_-6px_var(--color-accent)] transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          Reconnect GitHub
        </a>
      </main>
    )
  }

  if (skillsError) {
    return (
      <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
        <StatusPanel
          theme={{ ink: '#ff4d6a', glow: 'rgba(255,77,106,.28)' }}
          size="sm"
          className="w-full max-w-sm p-4 text-left text-sm"
        >
          <p className="text-danger-ink mb-3">Couldn't load the skill list: {skillsError}</p>
          <button
            type="button"
            onClick={() => setRetryToken((t) => t + 1)}
            className="bg-accent text-on-accent rounded-full px-4 py-2 font-medium transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            Try again
          </button>
        </StatusPanel>
      </main>
    )
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-6 px-6 text-center">
      <div>
        <p className="text-accent mb-1 font-mono text-xs tracking-[0.3em]">
          <SystemText>[ SKILL SELECTION ]</SystemText>
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-wide">Claim your skills</h1>
        <p className="text-ink-dim mt-1">
          Signed in as <span className="font-mono">{candidate?.github_login}</span>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-4">
        <SkillPicker skills={skills} selected={selected} onChange={setSelected} max={MAX_CLAIMED_SKILLS} />
        {skills.length === 0 && (
          <p className="text-ink-dim text-sm">No skills are available to claim right now. Check back soon.</p>
        )}

        <label className="text-ink-dim flex w-full items-center gap-2 text-left text-sm">
          <input
            type="checkbox"
            checked={searchable}
            onChange={(e) => setSearchable(e.target.checked)}
            className="accent-accent h-4 w-4"
          />
          Let recruiters find me in search
        </label>

        {error && <p className="text-danger-ink text-sm">{error}</p>}

        <button
          type="submit"
          disabled={selected.length === 0 || submitting}
          className="bg-accent text-on-accent w-full rounded-full px-6 py-3 font-medium shadow-[0_0_24px_-6px_var(--color-accent)] transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          {submitting ? 'Starting…' : `Verify ${selected.length || ''} skill${selected.length === 1 ? '' : 's'}`.trim()}
        </button>
      </form>
    </main>
  )
}
