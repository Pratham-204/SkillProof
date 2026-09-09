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
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.getMe).mockReset()
})

describe('Home', () => {
  it('renders the landing page without the Connect GitHub CTA for a logged-in candidate', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })

    const { findByText, queryByText } = renderHome()

    expect(await findByText('SkillProof')).toBeInTheDocument()
    expect(queryByText('Connect GitHub')).not.toBeInTheDocument()
  })

  it('shows the connect button for a logged-out visitor', async () => {
    vi.mocked(api.getMe).mockResolvedValue(null)

    const { findByText } = renderHome()

    expect(await findByText('Connect GitHub')).toBeInTheDocument()
  })

  it('does not show the connect button while the auth check is still in flight', () => {
    vi.mocked(api.getMe).mockReturnValue(new Promise(() => {}))

    const { queryByText } = renderHome()

    expect(queryByText('Connect GitHub')).not.toBeInTheDocument()
  })
})
