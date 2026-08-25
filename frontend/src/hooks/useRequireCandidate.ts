import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMe, type Candidate } from '../api'

interface RequireCandidateResult {
  candidate: Candidate | null
  loading: boolean
}

// Shared by every page that only renders for a logged-in Candidate: resolves
// the current session via `getMe()` and redirects to `/` if there isn't one.
// `loading` stays true until a real session resolves, so callers never
// briefly render as if logged out while the check is still in flight.
export function useRequireCandidate(): RequireCandidateResult {
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getMe().then((me) => {
      if (cancelled) return
      if (!me) {
        navigate('/', { replace: true })
        return
      }
      setCandidate(me)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [navigate])

  return { candidate, loading }
}
