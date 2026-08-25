import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, getMe: vi.fn(), getEvidenceCard: vi.fn() }
})

beforeEach(() => {
  window.history.pushState({}, '', '/')
})

describe('App navigation chrome', () => {
  it('shows the same header wordmark for a logged-out visitor', async () => {
    vi.mocked(api.getMe).mockResolvedValue(null)

    render(<App />)

    expect(await screen.findByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
  })

  it('shows the same header wordmark for a logged-in candidate, even after the post-login redirect', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })
    vi.mocked(api.getEvidenceCard).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
      cards: [],
    })

    render(<App />)

    expect(await screen.findByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
    // Confirms the redirect this header must survive actually happened.
    expect(window.location.pathname).toBe('/dashboard')
  })
})
