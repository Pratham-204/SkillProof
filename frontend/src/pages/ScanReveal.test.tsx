import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ScanReveal from './ScanReveal'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getMe: vi.fn(),
    getEvidenceCard: vi.fn(),
  }
})

const CANDIDATE = { candidate_id: 'cand-1', github_login: 'octodev', searchable: false, needs_reconnect: false }

function makeCard(skill: string, status: string): api.EvidenceCard {
  return {
    skill,
    status,
    error: null,
    confidence_score: status === 'complete' ? 0.8 : 0,
    evidence_type: 'verified',
    source_commits: [],
    temporal_span_days: 10,
    taxonomy_version: 1,
    explanation: null,
    explanation_is_fallback: false,
  }
}

// jsdom has no EventSource — this stands in for the real SSE connection, with
// `emit` letting a test fire scan/reveal/done events on demand.
class FakeEventSource {
  static instances: FakeEventSource[] = []
  private listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  closed = false
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  close() {
    this.closed = true
  }
  emit(type: string, data = '') {
    this.listeners[type]?.forEach((cb) => cb({ data } as MessageEvent))
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.mocked(api.getMe).mockResolvedValue(CANDIDATE)
})

function renderScanReveal() {
  return render(
    <MemoryRouter initialEntries={['/scan']}>
      <ScanReveal />
    </MemoryRouter>,
  )
}

describe('ScanReveal', () => {
  it('reaches completion by deriving its expected skills from the backend, with no location.state present', async () => {
    // Simulates landing on /scan directly (or via back/forward) rather than
    // via ClaimSkills' in-app navigation — MemoryRouter here carries no
    // `state`, so this only passes if completion no longer depends on it.
    const cardsDb = [makeCard('Python', 'processing'), makeCard('Rust', 'processing')]
    vi.mocked(api.getEvidenceCard).mockImplementation(async () => ({ ...CANDIDATE, cards: cardsDb }))

    renderScanReveal()

    await screen.findByText(/scanning your repos/i)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]

    // Cards revealed mid-scan aren't shown yet (still behind the scan-floor
    // timer) — just confirm each reveal event fetched the freshly-committed card.
    cardsDb[0] = makeCard('Python', 'complete')
    source.emit('reveal', 'Python')
    await waitFor(() => expect(api.getEvidenceCard).toHaveBeenCalledTimes(2))

    cardsDb[1] = makeCard('Rust', 'complete')
    source.emit('reveal', 'Rust')
    await waitFor(() => expect(api.getEvidenceCard).toHaveBeenCalledTimes(3))

    source.emit('done')

    expect(await screen.findByText('Your Evidence Cards', undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('Rust')).toBeInTheDocument()
  })

  it('reaches completion when verification already finished before this page ever loaded', async () => {
    // No card is "processing" at all (the run finished earlier) — the SSE
    // stream immediately sends "done" in this situation (see verify_stream),
    // and the fallback path should still surface the existing cards.
    const cardsDb = [makeCard('Python', 'complete')]
    vi.mocked(api.getEvidenceCard).mockImplementation(async () => ({ ...CANDIDATE, cards: cardsDb }))

    renderScanReveal()

    await screen.findByText(/scanning your repos/i)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]

    source.emit('done')

    expect(await screen.findByText('Your Evidence Cards', undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('sorts the "done" backfill alphabetically, regardless of the backend response order', async () => {
    // The backfill (used for any card that never fired its own "reveal" event
    // — every failed card, since verify_service._fail_card never publishes
    // one) must not depend on this endpoint's row order: that order is
    // score-descending, meant for the Dashboard/public card, not this live
    // view. Returns "Zebra" before "Apple" to prove the component re-sorts
    // locally rather than trusting the response order.
    const cardsDb = [makeCard('Zebra', 'failed'), makeCard('Apple', 'failed')]
    vi.mocked(api.getEvidenceCard).mockImplementation(async () => ({ ...CANDIDATE, cards: cardsDb }))

    renderScanReveal()

    await screen.findByText(/scanning your repos/i)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]

    source.emit('done')

    await screen.findByText('Your Evidence Cards', undefined, { timeout: 3000 })
    await screen.findByText('Zebra')
    const text = document.body.textContent ?? ''
    expect(text.indexOf('Apple')).toBeLessThan(text.indexOf('Zebra'))
  })

  it('does not complete before the "done" backfill lands, even if the expected count matched early', async () => {
    // Reproduces the undercount race: skill A finishes (and its "reveal"
    // event is missed — progress_bus doesn't replay events published before
    // this page subscribes) before the upfront "processing" snapshot
    // resolves, so that snapshot only ever sees skill B. Once B's own reveal
    // arrives, cards.length happens to equal the (undercounted) expected
    // length — completion must not fire on that coincidence; it must wait
    // for the "done" handler's own authoritative fetch.
    let resolveSnapshot: (v: api.CandidateEvidence) => void = () => {}
    let resolveReveal: (v: api.CandidateEvidence) => void = () => {}
    let resolveBackfill: (v: api.CandidateEvidence) => void = () => {}
    let call = 0
    vi.mocked(api.getEvidenceCard).mockImplementation(() => {
      const index = call
      call += 1
      return new Promise((resolve) => {
        if (index === 0) resolveSnapshot = resolve
        else if (index === 1) resolveReveal = resolve
        else resolveBackfill = resolve
      })
    })

    renderScanReveal()

    await screen.findByText(/scanning your repos/i)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]

    resolveSnapshot({ ...CANDIDATE, cards: [makeCard('B', 'processing')] })
    await waitFor(() => expect(api.getEvidenceCard).toHaveBeenCalledTimes(1))

    source.emit('reveal', 'B')
    await waitFor(() => expect(api.getEvidenceCard).toHaveBeenCalledTimes(2))
    resolveReveal({ ...CANDIDATE, cards: [makeCard('B', 'complete')] })

    source.emit('done')
    await waitFor(() => expect(api.getEvidenceCard).toHaveBeenCalledTimes(3))

    // Past the scan floor, "done" fired, and cards.length (1) already
    // matches the undercounted expected length (1) — but the backfill fetch
    // above is still unresolved, so this must still say "Revealing…". Waits
    // a beat past 'B' first appearing so any (buggy) cascading effect that
    // would flip to 'complete' anyway has a chance to have already run.
    await screen.findByText('B', undefined, { timeout: 3000 })
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(screen.getByText('Revealing…')).toBeInTheDocument()
    expect(screen.queryByText('Your Evidence Cards')).not.toBeInTheDocument()
    expect(screen.queryByText('A')).not.toBeInTheDocument()

    resolveBackfill({ ...CANDIDATE, cards: [makeCard('A', 'complete'), makeCard('B', 'complete')] })

    expect(await screen.findByText('Your Evidence Cards', undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })
})
