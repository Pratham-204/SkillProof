import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SkillTag } from '../api'
import SkillPicker from './SkillPicker'

const SKILLS: SkillTag[] = [
  { name: 'Python', category: 'language', description: 'The Python programming language.' },
  { name: 'FastAPI', category: 'framework', description: 'A Python web framework.' },
]

describe('SkillPicker', () => {
  it('lets a user search and select a skill', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SkillPicker skills={SKILLS} selected={[]} onChange={onChange} max={8} />)

    await user.type(screen.getByPlaceholderText('Search a skill…'), 'Fast')
    await user.click(screen.getByText('FastAPI'))

    expect(onChange).toHaveBeenCalledWith(['FastAPI'])
  })

  it('removes an already-selected skill when its chip is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SkillPicker skills={SKILLS} selected={['Python']} onChange={onChange} max={8} />)

    await user.click(screen.getByRole('button', { name: /Python/ }))

    expect(onChange).toHaveBeenCalledWith([])
  })

  it('disables input and hides matches once the max is reached', () => {
    render(<SkillPicker skills={SKILLS} selected={['Python']} onChange={vi.fn()} max={1} />)

    expect(screen.getByPlaceholderText('Limit of 1 skills reached')).toBeDisabled()
  })
})
