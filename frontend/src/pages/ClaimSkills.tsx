import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GITHUB_LOGIN_URL, MAX_CLAIMED_SKILLS, listSkills, verify, type SkillTag } from '../api'
import { useRequireCandidate } from '../hooks/useRequireCandidate'
import SkillPicker from '../components/SkillPicker'

export default function ClaimSkills() {
  const navigate = useNavigate()
  const { candidate, loading: authLoading } = useRequireCandidate()
  const [skills, setSkills] = useState<SkillTag[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [searchable, setSearchable] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [skillsLoading, setSkillsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listSkills().then((skillList) => {
      if (cancelled) return
      setSkills(skillList)
      setSkillsLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

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
        <h1 className="font-wordmark text-3xl">Reconnect GitHub</h1>
        <p className="text-neutral-500">
          Your GitHub access has been revoked, so verification can't run until you reconnect.
        </p>
        <a
          href={GITHUB_LOGIN_URL}
          className="rounded-full bg-neutral-900 px-6 py-3 font-medium text-white dark:bg-white dark:text-neutral-900"
        >
          Reconnect GitHub
        </a>
      </main>
    )
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-6 px-6 text-center">
      <div>
        <h1 className="font-wordmark text-3xl">Claim your skills</h1>
        <p className="mt-1 text-neutral-500">
          Signed in as <span className="font-mono">{candidate?.github_login}</span>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-4">
        <SkillPicker skills={skills} selected={selected} onChange={setSelected} max={MAX_CLAIMED_SKILLS} />

        <label className="flex w-full items-center gap-2 text-left text-sm text-neutral-600 dark:text-neutral-400">
          <input
            type="checkbox"
            checked={searchable}
            onChange={(e) => setSearchable(e.target.checked)}
            className="h-4 w-4"
          />
          Let recruiters find me in search
        </label>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={selected.length === 0 || submitting}
          className="w-full rounded-full bg-neutral-900 px-6 py-3 font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-neutral-900"
        >
          {submitting ? 'Starting…' : `Verify ${selected.length || ''} skill${selected.length === 1 ? '' : 's'}`.trim()}
        </button>
      </form>
    </main>
  )
}
