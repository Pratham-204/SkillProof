import { useEffect, useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import type { EvidenceCard } from '../api'
import { computeAchievements } from '../lib/achievements'
import { scoreToRank, RANK_THEME } from './system/rank'
import StatusPanel from './system/StatusPanel'
import RankBadge from './system/RankBadge'

interface HunterCardProps {
  githubLogin: string
  cards: EvidenceCard[]
}

// The hero "stats card" — one glance at the whole Hunter, not a single
// skill. Every number on it is a real aggregate over `cards` (the same list
// the tile list below renders); nothing here is a separately-scored concept.
export default function HunterCard({ githubLogin, cards }: HunterCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [avatarFailed, setAvatarFailed] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(false)

  // A public candidate card is mounted once at /c/:candidateId and reused
  // across client-side navigations between candidates (RecruiterSearch links
  // via <Link>), so this instance can outlive any one githubLogin — reset the
  // failure flag whenever the identity changes instead of carrying a stale
  // "this avatar is broken" verdict onto the next candidate's own avatar.
  useEffect(() => {
    setAvatarFailed(false)
  }, [githubLogin])

  const complete = cards.filter((c) => c.status === 'complete')
  const verifiedCount = complete.filter((c) => c.evidence_type === 'verified').length
  const totalEvidenceItems = complete.reduce((sum, c) => sum + c.source_commits.length, 0)
  const longestSpanDays = Math.max(0, ...complete.map((c) => c.temporal_span_days))
  const avgScore = complete.length ? complete.reduce((sum, c) => sum + c.confidence_score, 0) / complete.length : 0
  const overallRank = scoreToRank(avgScore, 'verified')
  const theme = RANK_THEME[overallRank]
  const achievements = computeAchievements(cards)

  async function handleDownload() {
    if (!cardRef.current || exporting) return
    setExporting(true)
    setExportError(false)
    try {
      // Wait for the real webfonts to finish loading first — otherwise an
      // early click can rasterize the card in fallback system fonts with no
      // error, silently producing an off-brand PNG.
      if (document.fonts?.ready) {
        await document.fonts.ready
      }
      const dataUrl = await toPng(cardRef.current, {
        backgroundColor: '#05070d',
        pixelRatio: 2,
      })
      // iOS/iPadOS Safari doesn't reliably honor `download` on a `data:` URI
      // — the click can silently no-op with no file saved and nothing to
      // catch, so give it a way to actually save the image: opening the data
      // URL directly lets the user use the share/save sheet on the image.
      const isIOS = /iP(hone|od|ad)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
      if (isIOS) {
        window.open(dataUrl, '_blank')
      } else {
        const link = document.createElement('a')
        link.href = dataUrl
        link.download = `skillproof-${githubLogin}.png`
        // Appending (then removing) the anchor before clicking is required
        // for the `download` attribute to be honored in some browsers.
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }
    } catch {
      setExportError(true)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <StatusPanel theme={theme} className="w-full max-w-sm p-6 text-center">
        {/* Exports as a plain rectangle, not the panel's own clipped corners —
            clip-path support in DOM-to-image export is unreliable across
            browsers, so the captured node is this inner, unclipped div. */}
        <div ref={cardRef} className="bg-surface flex flex-col items-center gap-4 p-2">
          <p className="text-accent font-mono text-xs tracking-[0.3em]">[ HUNTER LICENSE ]</p>

          <div className="relative">
            <div
              className="h-24 w-24 rounded-full"
              style={{ boxShadow: `0 0 0 2px ${theme.ink}, 0 0 28px -4px ${theme.glow}` }}
            >
              {!avatarFailed ? (
                // crossOrigin="anonymous" is required for the export path
                // below: html-to-image rasterizes this element to a canvas,
                // and a cross-origin image loaded without CORS taints that
                // canvas — toPng() then throws a SecurityError on every
                // export, always caught by the try/catch as a generic
                // failure. github.com/{login}.png redirects to
                // avatars.githubusercontent.com, which does send
                // `Access-Control-Allow-Origin: *` (verified directly), so a
                // CORS-mode request here loads the same image without
                // tainting anything.
                <img
                  src={`https://github.com/${githubLogin}.png?size=200`}
                  alt=""
                  crossOrigin="anonymous"
                  onError={() => setAvatarFailed(true)}
                  className="h-full w-full rounded-full object-cover"
                />
              ) : (
                <div
                  className="bg-surface-2 text-ink-dim font-display flex h-full w-full items-center justify-center rounded-full text-3xl font-bold"
                  aria-hidden="true"
                >
                  {githubLogin.charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <div className="absolute -bottom-2 -right-2">
              <RankBadge rank={overallRank} size="lg" title={`Overall rank ${overallRank}`} />
            </div>
          </div>

          <h1 className="font-display break-words text-2xl font-bold tracking-wide">{githubLogin}</h1>

          <div className="grid w-full grid-cols-4 gap-2 border-t border-edge pt-4">
            <Stat value={complete.length} label="Skills" />
            <Stat value={verifiedCount} label="Verified" />
            <Stat value={totalEvidenceItems} label="Evidence" />
            <Stat value={longestSpanDays} label="Days" />
          </div>
        </div>
      </StatusPanel>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleDownload}
          disabled={exporting}
          className="border-edge text-ink-dim hover:border-accent hover:text-accent-ink focus-visible:outline-accent flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm transition-colors disabled:cursor-wait focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          {exporting ? 'Preparing…' : 'Download my card'}
        </button>
      </div>
      {exportError && <p className="text-danger-ink text-xs">Could not export the card — try again.</p>}

      {achievements.length > 0 && (
        <StatusPanel size="sm" className="w-full max-w-sm p-4 text-left">
          <p className="text-accent mb-3 font-mono text-xs tracking-[0.3em]">[ TROPHY CABINET ]</p>
          <ul className="flex flex-col gap-2">
            {achievements.map((a) => (
              <li key={a.id} className="flex items-start gap-2">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${a.id === 's-rank' ? 'bg-gold' : 'bg-accent'}`}
                  aria-hidden="true"
                />
                <span>
                  <span className="font-medium">{a.label}</span>
                  <span className="text-ink-dim block text-xs">{a.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </StatusPanel>
      )}
    </div>
  )
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex min-w-0 flex-col items-center gap-0.5">
      <span className="text-accent-ink font-mono text-lg font-semibold tabular-nums">{value}</span>
      <span className="text-ink-dim [overflow-wrap:anywhere] text-center text-[0.65rem] uppercase">{label}</span>
    </div>
  )
}
