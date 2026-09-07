import type { CSSProperties, ReactNode } from 'react'
import type { RankTheme } from './rank'

interface StatusPanelProps {
  children: ReactNode
  /** Drives the panel's border/glow color — pass a RankTheme, or omit for the neutral default edge. */
  theme?: RankTheme
  size?: 'md' | 'sm'
  className?: string
  as?: 'div' | 'li'
}

// The one panel primitive every card/section in the app is built from —
// angular clipped corners instead of a rounded rectangle, glow intensity
// driven by rank so a low-confidence claim visibly reads as "dormant" and a
// high one as "lit up", not just a different number in the same box.
export default function StatusPanel({ children, theme, size = 'md', className = '', as = 'div' }: StatusPanelProps) {
  const style: CSSProperties = theme
    ? ({ '--sp-edge': theme.ink, '--sp-glow': theme.glow } as CSSProperties)
    : {}
  const Tag = as
  return (
    <Tag className={`status-panel ${size === 'sm' ? 'status-panel--sm' : ''} ${className}`} style={style}>
      {children}
    </Tag>
  )
}
