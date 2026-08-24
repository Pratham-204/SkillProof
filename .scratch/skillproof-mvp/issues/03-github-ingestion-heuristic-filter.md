# 03 — GitHub evidence ingestion + heuristic filter

**What to build:** Given a connected Candidate, pull their commit diffs and PR review comments from public repos, respecting GitHub's rate limits, then prune out low-signal evidence before anything gets embedded.

**Blocked by:** 01 (needs a Candidate + stored token to fetch on behalf of).

**Status:** done

- [x] Commit diffs and PR review comments are pulled from the Candidate's owned public, non-fork repos.
- [x] Evidence is also pulled from external repos where the Candidate has at least one merged PR, discovered via the GitHub Search/Events API.
- [x] GitHub API calls use conditional requests (ETags) and exponential backoff on secondary rate limits.
- [x] Commits that touch only docs/config files are dropped before scoring.
- [x] PR comments under 10 words are dropped before scoring.
- [x] Private repositories are never accessed.

## Comments

- Round 9 (CONTEXT.md): the low-effort PR-comment word floor was lowered from 10 to 5 words (`heuristics.MIN_PR_COMMENT_WORDS`) — the checklist item above reflects the original ticket, this repo's current behavior is 5.
