import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ClaimSkills from './ClaimSkills'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getMe: vi.fn(),
    listSkills: vi.fn(),
    verify: vi.fn(),
  }
})

const SKILLS = [
  { name: 'Go', category: 'language', description: 'The Go programming language.' },
  { name: 'Python', category: 'language', description: 'The Python programming language.' },
]

beforeEach(() => {
  vi.mocked(api.listSkills).mockResolvedValue(SKILLS)
  vi.mocked(api.verify).mockResolvedValue(undefined)
})

function renderClaim() {
  return render(
    <MemoryRouter>
      <ClaimSkills />
    </MemoryRouter>,
  )
}

describe('ClaimSkills', () => {
  it('defaults the searchable checkbox to unchecked for a candidate not yet searchable', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: false,
      needs_reconnect: false,
    })
    renderClaim()

    const toggle = await screen.findByRole('checkbox', { name: /recruiters find me/i })
    expect(toggle).not.toBeChecked()
  })

  // Regression: claiming more skills used to always submit `searchable: false`
  // regardless of the candidate's existing setting, silently opting an
  // already-searchable candidate back out (this form's local state started at
  // `false` and was never seeded from the loaded candidate).
  it('seeds the searchable checkbox from an already-searchable candidate, and submits that value unchanged', async () => {
    const user = userEvent.setup()
    vi.mocked(api.getMe).mockResolvedValue({
      candidate_id: 'cand-1',
      github_login: 'octodev',
      searchable: true,
      needs_reconnect: false,
    })
    renderClaim()

    const toggle = await screen.findByRole('checkbox', { name: /recruiters find me/i })
    await waitFor(() => expect(toggle).toBeChecked())

    await user.type(screen.getByPlaceholderText(/search a skill/i), 'Go')
    await user.click(await screen.findByText('Go'))
    await user.click(screen.getByRole('button', { name: /verify 1 skill/i }))

    expect(api.verify).toHaveBeenCalledWith(['Go'], true)
  })
})
