import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GITHUB_LOGIN_URL, getMe } from '../api'

export default function Home() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    getMe().then((candidate) => {
      if (cancelled) return
      if (candidate) {
        navigate('/dashboard', { replace: true })
      } else {
        setChecking(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [navigate])

  return (
    <main className="mx-auto flex min-h-svh max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="font-wordmark text-6xl">SkillProof</h1>
      <p className="max-w-md text-neutral-500">
        Connect GitHub, claim the skills you want verified, and get a public Evidence Card built from your real
        commit and PR history — not a resume line.
      </p>
      {!checking && (
        <a
          href={GITHUB_LOGIN_URL}
          className="rounded-full bg-neutral-900 px-6 py-3 font-medium text-white transition hover:bg-neutral-700 dark:bg-white dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          Connect GitHub
        </a>
      )}
    </main>
  )
}
