import { useId, useMemo, useState, type KeyboardEvent } from 'react'
import type { SkillTag } from '../api'
import StatusPanel from './system/StatusPanel'

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
  // Index into `matches` the user has moved to via ArrowUp/ArrowDown; -1 means
  // "nothing highlighted yet". Drives aria-activedescendant so a screen-reader
  // user hears which option is current without focus ever leaving the input.
  const [highlighted, setHighlighted] = useState(-1)
  const listboxId = useId()

  const atLimit = selected.length >= max

  const matches = useMemo(() => {
    if (!query.trim() || atLimit) return []
    const lower = query.toLowerCase()
    return skills.filter((s) => !selected.includes(s.name) && s.name.toLowerCase().includes(lower)).slice(0, 8)
  }, [query, skills, selected, atLimit])

  const isOpen = matches.length > 0
  const activeOptionId =
    highlighted >= 0 && highlighted < matches.length ? `${listboxId}-option-${highlighted}` : undefined

  function add(name: string) {
    if (atLimit || selected.includes(name)) return
    onChange([...selected, name])
    setQuery('')
    setHighlighted(-1)
  }

  function remove(name: string) {
    onChange(selected.filter((s) => s !== name))
  }

  // WAI-ARIA APG "combobox with list autocomplete" keyboard contract: arrow
  // keys move a virtual selection without stealing DOM focus from the input,
  // Enter commits whatever is highlighted, Escape drops the highlight.
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((i) => (i + 1) % matches.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((i) => (i <= 0 ? matches.length - 1 : i - 1))
    } else if (e.key === 'Enter') {
      if (highlighted >= 0 && highlighted < matches.length) {
        e.preventDefault()
        add(matches[highlighted].name)
      }
    } else if (e.key === 'Escape') {
      setHighlighted(-1)
    }
  }

  return (
    <div className="w-full text-left">
      <div className="mb-2 flex flex-wrap gap-2">
        {selected.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => remove(name)}
            aria-label={`Remove ${name}`}
            className="border-accent/50 bg-accent-soft text-accent-ink hover:border-accent hover:bg-accent-soft/80 focus-visible:outline-accent flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-sm transition-colors active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            {name}
            <span aria-hidden="true" className="opacity-70">
              &times;
            </span>
          </button>
        ))}
      </div>

      {/* The field itself intentionally stays a plain rounded input rather than
          adopting StatusPanel's clip-path chrome: StatusPanel's corner cut only
          composes onto a div/li wrapper, and this is the app's one free-text
          entry control (autocomplete-only, per the note above) rather than a
          status readout. The dropdown of results below it — the part that
          actually reads as a "panel" — does adopt the angular treatment. */}
      <input
        type="text"
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeOptionId}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlighted(-1)
        }}
        onKeyDown={handleKeyDown}
        placeholder={atLimit ? `Limit of ${max} skills reached` : 'Search a skill…'}
        disabled={atLimit}
        className="border-edge bg-surface text-ink focus:border-accent placeholder:text-ink-dim disabled:bg-surface-2 w-full rounded-lg border px-4 py-2 outline-none disabled:cursor-not-allowed"
      />
      <p className="text-ink-dim mt-1 font-mono text-xs tabular-nums">
        {selected.length} / {max} selected
      </p>
      {/* Visually hidden live region: announces match count changes to screen
          readers, since aria-expanded alone isn't reliably announced on every
          input event. */}
      <p aria-live="polite" className="sr-only">
        {isOpen ? `${matches.length} matching skill${matches.length === 1 ? '' : 's'} found` : ''}
      </p>

      {isOpen && (
        <StatusPanel size="sm" as="div" className="mt-1">
          <ul id={listboxId} role="listbox" className="max-h-56 overflow-y-auto">
            {matches.map((skill, index) => (
              <li
                key={skill.name}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={highlighted === index}
                onMouseEnter={() => setHighlighted(index)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => add(skill.name)}
                className={`block w-full cursor-pointer px-4 py-2 text-left ${
                  highlighted === index ? 'bg-surface-2' : 'hover:bg-surface-2'
                }`}
              >
                <span className="font-medium">{skill.name}</span>{' '}
                <span className="text-ink-dim text-xs">{skill.category}</span>
              </li>
            ))}
          </ul>
        </StatusPanel>
      )}
    </div>
  )
}
