import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'framer-motion'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* reducedMotion="user" makes every framer-motion animation in the tree
        (ScoreCounter's count-up, EvidenceCardList/Tile's stagger-in, ScanReveal's
        motion.p/motion.li fades) collapse to instant when the OS reduced-motion
        setting is on, matching the discipline already applied to SystemText and
        the CSS-driven .reveal-in/.system-glow-pulse keyframes. */}
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>,
)
