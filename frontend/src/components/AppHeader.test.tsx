import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import AppHeader from './AppHeader'

describe('AppHeader', () => {
  it('renders a wordmark link back to the home page', () => {
    render(
      <MemoryRouter>
        <AppHeader />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /skillproof/i })).toHaveAttribute('href', '/')
  })
})
