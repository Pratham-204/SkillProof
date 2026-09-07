import { animate, useMotionValue } from 'framer-motion'
import { useEffect, useState } from 'react'

interface ScoreCounterProps {
  /** Confidence Score in [0,1] — displayed as a count-up percentage. */
  score: number
  className?: string
}

// useMotionValue + animate with a custom deceleration curve, per the design
// brief — not react-countup, which wouldn't give control over the easing.
export default function ScoreCounter({ score, className }: ScoreCounterProps) {
  const motionValue = useMotionValue(0)
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const target = Math.round(score * 100)
    const controls = animate(motionValue, target, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(Math.round(v)),
    })
    return () => controls.stop()
  }, [score, motionValue])

  // tabular-nums is load-bearing here: without it, digit width changes as
  // the count-up runs and the number visibly jitters left/right. Reads as a
  // System readout: monospace glyphs, accent-lit, currentColor so a caller
  // passing a dim/weak className (e.g. opacity-60) still dims the glow with it.
  return (
    <span
      className={`font-mono tabular-nums text-accent-ink ${className ?? ''}`}
      style={{ textShadow: '0 0 12px currentColor' }}
    >
      {display}
      <span className="text-[0.6em] opacity-60">%</span>
    </span>
  )
}
