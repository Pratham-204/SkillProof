import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GITHUB_LOGIN_URL, getMe } from '../api'
import SystemText from '../components/system/SystemText'

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
    <main className="mx-auto flex min-h-svh max-w-xl flex-col items-center justify-center gap-8 px-6 text-center">
      <p className="text-accent font-mono text-xs tracking-[0.3em]">
        <SystemText delayMs={100}>[ SYSTEM ]</SystemText>
      </p>
      <h1 className="font-display text-6xl font-bold tracking-wide">
        <SystemText delayMs={350}>SkillProof</SystemText>
      </h1>
      <p className="text-ink-dim max-w-md text-balance">
        Connect GitHub, claim the skills you want verified, and get a public Evidence Card built from your real
        commit and PR history — not a resume line.
      </p>
      {!checking && (
        <a
          href={GITHUB_LOGIN_URL}
          className="bg-accent text-on-accent rounded-full px-6 py-3 font-medium shadow-[0_0_24px_-6px_var(--color-accent)] transition hover:opacity-90 active:scale-[0.98] active:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          Connect GitHub
        </a>
      )}
    </main>
  )
}
