import { useEffect, useRef, useState } from 'react'

interface SystemTextProps {
  children: string
  className?: string
  /** Delay before this line starts revealing, in ms — lets a caller stagger several lines. */
  delayMs?: number
}

// A single short line of REAL text (a phase label, a repo name, a skill tag)
// materializing left-to-right like a status-window log line, instead of a
// plain fade-in. This never fabricates content — callers pass the real
// string; it only changes how that string arrives on screen. Intended for
// short labels, not paragraph text (it forces `whitespace-nowrap` so the
// wipe reads as one clean line).
export default function SystemText({ children, className = '', delayMs = 0 }: SystemTextProps) {
  const [revealed, setRevealed] = useState(false)
  const reducedMotion = useRef(
    typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    if (reducedMotion.current) {
      setRevealed(true)
      return
    }
    const timer = setTimeout(() => setRevealed(true), delayMs)
    return () => clearTimeout(timer)
  }, [delayMs])

  return (
    <span
      className={`inline-block max-w-full overflow-hidden whitespace-nowrap align-bottom ${className}`}
      style={{
        clipPath: revealed ? 'inset(0 0% 0 0)' : 'inset(0 100% 0 0)',
        transition: 'clip-path 0.5s steps(20, end)',
      }}
    >
      {children}
    </span>
  )
}
