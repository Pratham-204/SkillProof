import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import AppHeader from './AppHeader'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, getMe: vi.fn() }
})

beforeEach(() => {
  vi.mocked(api.getMe).mockReset()
})

function renderHeader(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AppHeader />
    </MemoryRouter>,
  )
}

describe('AppHeader', () => {
  it('renders a wordmark link back to the home page for a logged-out visitor', async () => {
    vi.mocked(api.getMe).mockResolvedValue(null)

    renderHeader('/')

    expect(screen.getByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('link', { name: /octodev/i })).not.toBeInTheDocument()
  })

  it('shows a link to the Dashboard with the candidate login once signed in', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })

    renderHeader('/claim')

    expect(await screen.findByRole('link', { name: /octodev/i })).toHaveAttribute('href', '/dashboard')
    // The wordmark stays present and unchanged alongside it.
    expect(screen.getByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
  })

  it('never shows the identity link on the public Evidence Card route, even when signed in', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })

    renderHeader('/c/cand-1')

    // Give any (unexpected) async identity fetch a chance to resolve before
    // asserting its absence — this must stay negative regardless.
    await Promise.resolve()
    expect(api.getMe).not.toHaveBeenCalled()
    expect(screen.queryByRole('link', { name: /octodev/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
  })
})
