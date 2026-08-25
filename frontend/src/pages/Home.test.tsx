import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Home from './Home'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, getMe: vi.fn() }
})

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<div>Dashboard page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.getMe).mockReset()
})

describe('Home', () => {
  it('redirects a logged-in candidate to the dashboard', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })

    const { findByText } = renderHome()

    expect(await findByText('Dashboard page')).toBeInTheDocument()
  })

  it('shows the connect button for a logged-out visitor', async () => {
    vi.mocked(api.getMe).mockResolvedValue(null)

    const { findByText } = renderHome()

    expect(await findByText('Connect GitHub')).toBeInTheDocument()
  })
})
