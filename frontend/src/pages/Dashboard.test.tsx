import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Dashboard from './Dashboard'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getMe: vi.fn(),
    getEvidenceCard: vi.fn(),
    updateSearchable: vi.fn(),
  }
})

const CANDIDATE = { candidate_id: 'cand-1', github_login: 'octodev', searchable: false, needs_reconnect: false }
const CARDS = [
  {
    skill: 'Python',
    status: 'complete',
    error: null,
    confidence_score: 0.8,
    evidence_type: 'verified' as const,
    source_commits: [],
    temporal_span_days: 10,
    taxonomy_version: 1,
    explanation: null,
    explanation_is_fallback: false,
  },
]

beforeEach(() => {
  vi.mocked(api.getMe).mockResolvedValue(CANDIDATE)
  vi.mocked(api.getEvidenceCard).mockResolvedValue({ ...CANDIDATE, cards: CARDS })
})

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

describe('Dashboard', () => {
  it("renders the candidate's existing Evidence Cards", async () => {
    renderDashboard()

    expect(await screen.findByText('Python')).toBeInTheDocument()
  })

  it('toggles searchable and reflects the persisted state', async () => {
    const user = userEvent.setup()
    vi.mocked(api.updateSearchable).mockResolvedValue({ ...CANDIDATE, searchable: true })
    renderDashboard()
    await screen.findByText('Python')

    const toggle = screen.getByRole('checkbox', { name: /recruiters find me/i })
    expect(toggle).not.toBeChecked()

    await user.click(toggle)

    await waitFor(() => expect(toggle).toBeChecked())
    expect(api.updateSearchable).toHaveBeenCalledWith(true)
  })

  it('shows a copyable link to the public Evidence Card', async () => {
    const user = userEvent.setup()
    // user-event installs its own navigator.clipboard on setup() — redefine
    // the spy afterward so it's the one Dashboard's copy button actually calls.
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    renderDashboard()
    await screen.findByText('Python')

    expect(screen.getByText(/\/c\/cand-1/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /copy link/i }))

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/c/cand-1'))
  })

  it('offers a "claim more skills" action', async () => {
    renderDashboard()
    await screen.findByText('Python')

    expect(screen.getByRole('link', { name: /claim more skills/i })).toHaveAttribute('href', '/claim')
  })

  it('shows a reconnect prompt when needs_reconnect is set', async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...CANDIDATE, needs_reconnect: true })
    renderDashboard()

    expect(await screen.findByText(/reconnect github/i)).toBeInTheDocument()
  })

  it('reflects the toggle immediately, before the network call resolves', async () => {
    const user = userEvent.setup()
    let resolveUpdate: (candidate: typeof CANDIDATE) => void = () => {}
    vi.mocked(api.updateSearchable).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpdate = resolve
        }),
    )
    renderDashboard()
    await screen.findByText('Python')

    const toggle = screen.getByRole('checkbox', { name: /recruiters find me/i })
    await user.click(toggle)

    expect(toggle).toBeChecked()

    resolveUpdate({ ...CANDIDATE, searchable: true })
    await waitFor(() => expect(api.updateSearchable).toHaveBeenCalledWith(true))
  })

  it('rolls the toggle back if the update fails', async () => {
    const user = userEvent.setup()
    vi.mocked(api.updateSearchable).mockRejectedValue(new Error('boom'))
    renderDashboard()
    await screen.findByText('Python')

    const toggle = screen.getByRole('checkbox', { name: /recruiters find me/i })
    await user.click(toggle)

    await waitFor(() => expect(toggle).not.toBeChecked())
  })
})
