import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import ClaimSkills from './pages/ClaimSkills'
import ScanReveal from './pages/ScanReveal'
import PublicEvidenceCard from './pages/PublicEvidenceCard'
import RecruiterSearch from './pages/RecruiterSearch'

// Route naming deliberately avoids the backend's API path prefixes
// (/auth, /verify, /evidence-card, /explain, /search, /skills) — the dev
// proxy (vite.config.ts) forwards those prefixes to FastAPI, so a frontend
// route reusing one would be shadowed by the API on direct navigation/refresh.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/claim" element={<ClaimSkills />} />
        <Route path="/scan" element={<ScanReveal />} />
        <Route path="/c/:candidateId" element={<PublicEvidenceCard />} />
        <Route path="/find" element={<RecruiterSearch />} />
      </Routes>
    </BrowserRouter>
  )
}
