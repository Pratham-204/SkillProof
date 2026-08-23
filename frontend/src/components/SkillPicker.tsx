import { useMemo, useState } from 'react'
import type { SkillTag } from '../api'

interface SkillPickerProps {
  skills: SkillTag[]
  selected: string[]
  onChange: (skills: string[]) => void
  max: number
}

// Autocomplete-only by design (CONTEXT.md: "Candidates claim skills by
// selecting Skill Tags via autocomplete, not by typing free text") — there is
// no way to add a skill that isn't an exact match from `skills`.
export default function SkillPicker({ skills, selected, onChange, max }: SkillPickerProps) {
  const [query, setQuery] = useState('')

  const atLimit = selected.length >= max

  const matches = useMemo(() => {
    if (!query.trim() || atLimit) return []
    const lower = query.toLowerCase()
    return skills.filter((s) => !selected.includes(s.name) && s.name.toLowerCase().includes(lower)).slice(0, 8)
  }, [query, skills, selected, atLimit])

  function add(name: string) {
    if (atLimit || selected.includes(name)) return
    onChange([...selected, name])
    setQuery('')
  }

  function remove(name: string) {
    onChange(selected.filter((s) => s !== name))
  }

  return (
    <div className="w-full text-left">
      <div className="mb-2 flex flex-wrap gap-2">
        {selected.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => remove(name)}
            className="flex items-center gap-1 rounded-full bg-neutral-900 px-3 py-1 text-sm text-white dark:bg-white dark:text-neutral-900"
          >
            {name}
            <span aria-hidden="true">&times;</span>
          </button>
        ))}
      </div>

      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={atLimit ? `Limit of ${max} skills reached` : 'Search a skill…'}
        disabled={atLimit}
        className="w-full rounded-lg border border-neutral-300 px-4 py-2 outline-none focus:border-neutral-900 disabled:bg-neutral-100 dark:border-neutral-700 dark:bg-transparent dark:focus:border-white dark:disabled:bg-neutral-900"
      />
      <p className="mt-1 text-xs text-neutral-500 tabular-nums">
        {selected.length} / {max} selected
      </p>

      {matches.length > 0 && (
        <ul className="mt-1 max-h-56 overflow-y-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          {matches.map((skill) => (
            <li key={skill.name}>
              <button
                type="button"
                onClick={() => add(skill.name)}
                className="block w-full px-4 py-2 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
              >
                <span className="font-medium">{skill.name}</span>{' '}
                <span className="text-xs text-neutral-500">{skill.category}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
