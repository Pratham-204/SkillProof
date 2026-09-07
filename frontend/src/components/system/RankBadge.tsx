import type { CSSProperties } from 'react'
import { RANK_THEME, type RankLetter } from './rank'

interface RankBadgeProps {
  rank: RankLetter
  size?: 'sm' | 'md' | 'lg'
  title?: string
}

const SIZE_CLASS: Record<NonNullable<RankBadgeProps['size']>, string> = {
  sm: 'h-6 w-6 text-xs',
  md: 'h-9 w-9 text-base',
  lg: 'h-14 w-14 text-2xl',
}

// A hunter-license rank badge (E through S) — the hex-clipped equivalent of
// a FUT card's rating corner, bucketed client-side from confidence_score
// (see rank.ts). Purely presentational: the letter is never sent anywhere.
export default function RankBadge({ rank, size = 'md', title }: RankBadgeProps) {
  const theme = RANK_THEME[rank]
  const style = { '--rb-ink': theme.ink, '--rb-glow': theme.glow } as CSSProperties
  return (
    <span
      className={`rank-badge shrink-0 ${SIZE_CLASS[size]}`}
      style={style}
      data-rank={rank}
      title={title ?? `Rank ${rank}`}
      aria-label={title ?? `Rank ${rank}`}
    />
  )
}
