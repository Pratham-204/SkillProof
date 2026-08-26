# 06 — ScanReveal completion-detection fix

**What to build:** `ScanReveal` currently reads its expected skill list from React Router's `location.state`, which only exists if the page was reached via one specific in-app navigation. Using the browser's back button, refreshing, or landing on the page any other way silently loses that state and changes completion behavior. Make completion detection derive from the Candidate's own backend state instead, so it's correct regardless of how the page was reached.

**Blocked by:** 01 (shared Candidate hook), 02 (frontend test infrastructure)

**Status:** done

- [x] `ScanReveal`'s "am I done" check derives its expected skill set from the Candidate's own Evidence Cards with `status === "processing"`, fetched from the backend, rather than from router `location.state`.
- [x] Visiting the scan/reveal page directly, or reaching it via back/forward navigation (i.e. with no `location.state` present), still reaches the correct complete/incomplete state.
- [x] The existing SSE-driven scan/reveal/done event handling is unchanged — only the completion check's data source changes.
- [x] `ScanReveal` resolves the current Candidate via the shared hook from ticket 01.
- [x] Covered by a component test that simulates a visit with no `location.state` present and asserts the page still reaches the correct completion state.
