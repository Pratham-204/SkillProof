# Speed Up GitHub Evidence Scanning

Status: done

## Problem Statement

Verifying a candidate's claimed skills means scanning their GitHub history for evidence, and that scan is slow enough to be a real product problem — candidates and recruiters wait far longer than the work being done should require. The scan is entirely sequential HTTP calls through `httpx` in `src/skillproof/github_client.py` (no repo cloning, no SDK) and the slowness comes from architecture, not from the transport itself:

1. **Per-filename manifest probing.** `get_manifest_files` (github_client.py:285-297) issues one `GET /repos/{full_name}/contents/{filename}` per hardcoded manifest filename (up to 20, github_client.py:17-38), per repo, one after another.
2. **Per-commit diff fetch (N+1).** `_commit_record` (257-269) makes a separate `GET /repos/{full_name}/commits/{sha}` for every commit to pull its diff, called from list comprehensions in `_fetch_owned_commits` and `_fetch_pr_commits` (249, 255) — so the call count scales linearly with commit count.
3. **Zero concurrency anywhere.** `ingest_evidence` (ingestion.py:66-104) and `list_qualifying_commits` (github_client.py:125-162) walk owned repos, merged PRs, manifests, commits, and PR review comments entirely one at a time, with no batching or parallel requests at any level.
4. **In-line, blocking rate-limit backoff.** When GitHub responds 403/rate-limited, `_fetch_page` (324-350) sleeps synchronously (up to `max_retries=5`) right in the request path, stalling the whole scan rather than backing off around other work.
5. **Serial repo-by-repo iteration.** Each owned or merged-PR repo is fully processed (paginated commit list + every commit's detail) before the next repo starts.

Pagination (`Link`-header following, capped at 100 pages) and ETag-based re-fetch avoidance already exist and are not the problem — they stay as-is.

## Solution

Introduce bounded concurrency at the two N+1 hot paths (manifest probing and per-commit detail fetch) and across repo iteration, using a thread pool sized to the shared GitHub rate-limit budget, so the scan issues many requests in flight instead of one at a time. Make rate-limit backoff a shared, cooperative wait instead of a per-call blocking sleep, so one call's backoff doesn't leave (or wake up) other calls with stale rate-limit state. No change to what evidence is collected or how it's scored — this is purely a throughput restructuring of the same requests already being made.

## User Stories

**Manifest fetch concurrency**

1. As a Candidate, I want manifest-file detection to check all ~20 filenames for a repo concurrently instead of one at a time, so that step of my scan finishes in roughly one request's latency instead of twenty.

**Commit detail fetch concurrency**

2. As a Candidate with a long commit history, I want my qualifying commits' diffs fetched concurrently, so scan time stops scaling linearly with how many commits I have.

**Repo iteration concurrency**

3. As a Candidate with multiple owned repos and merged PRs, I want those repos processed concurrently rather than one fully finishing before the next starts, so my total scan time is closer to the slowest single repo than the sum of all of them.

**Shared rate-limit handling**

4. As a developer, I want rate-limit backoff to be shared across all in-flight requests (one cooldown, respected by every worker) rather than each call independently sleeping and re-discovering the same 403, so concurrency doesn't multiply wasted backoff time or trip the rate limit harder than sequential code did.
5. As a Candidate, I want a rate-limit cooldown to only pause the requests actually affected, not silently freeze the entire scan job the way today's in-line `time.sleep` does.

**Correctness preserved**

6. As a developer, I want every existing test in `tests/` covering ingestion, GitHub client pagination, ETag caching, and ordering/dedup behavior to keep passing unchanged, so this is provably a pure performance restructuring with no behavior change.
7. As a developer, I want concurrent requests to still respect the existing 100-page pagination cap and ETag cache, so those existing protections aren't silently bypassed by parallelizing the calls around them.

## Implementation Decisions

- **Concurrency primitive.** Use `concurrent.futures.ThreadPoolExecutor` (not `asyncio`) to avoid an async rewrite of `RealGitHubClient` and the rest of the ingestion pipeline; `httpx.Client` is documented thread-safe for concurrent use from multiple threads against one client instance.
- **Bounded worker count.** Cap concurrent in-flight requests (e.g. 8-10 workers) well under GitHub's per-token rate limit, applied uniformly across manifest probing, commit-detail fetch, and repo iteration — not per-call unbounded parallelism.
- **Shared rate-limit gate.** Replace the per-call `_backoff_seconds`/`time.sleep` in `_fetch_page` with a shared gate (e.g. a `threading.Event` plus a stored "resume at" timestamp) that every worker checks before issuing a request: the first worker to see `X-RateLimit-Remaining: 0` sets the gate until `X-RateLimit-Reset`, and other workers wait on that single gate instead of each sleeping and re-hitting the same 403.
- **Manifest fetch.** `get_manifest_files` submits all ~20 filename lookups to the thread pool and gathers results, preserving today's per-repo return shape.
- **Commit detail fetch.** `_fetch_owned_commits` / `_fetch_pr_commits` submit each commit's `_commit_record` call to the thread pool instead of building the list comprehension serially; results are reassembled in original commit order before returning (order matters for existing dedup/ordering behavior downstream).
- **Repo iteration.** `list_qualifying_commits` and `ingest_evidence`'s per-repo loops move to bounded concurrent processing of repos, each repo's own manifest/commit work still using the same shared thread pool and rate-limit gate rather than spinning up a pool per repo.
- **No GraphQL migration in this pass.** Switching to GitHub's GraphQL API (batching commit/file queries into one round trip) would cut request count further but is a larger, separate change to the client's request shape; this spec only reduces wall-clock time for the existing REST calls via concurrency.

## Testing Decisions

- Existing test seams (`tests/` covering `github_client.py`, ingestion, and API flow) must pass unchanged — concurrency must not change what's fetched, in what order it's returned, or how it's scored.
- Add a dedicated test proving manifest fetch and commit-detail fetch issue requests concurrently (e.g. asserting overlapping in-flight requests via a fake transport with controllable delays), not just that they still return correct results serially.
- Add a test proving the shared rate-limit gate: simulate one worker hitting `X-RateLimit-Remaining: 0`, assert other concurrent workers wait on the same cooldown rather than each independently sleeping and re-requesting.
- Add a test proving the 100-page pagination cap and ETag cache behavior are unchanged under concurrent execution.

## Out of Scope

- Migrating to GitHub's GraphQL API — a real further speedup but a separate, larger change to the request shape; noted here as likely future follow-on work.
- Any change to what evidence is collected, how manifest files are matched, or how confidence scoring works.
- Firecrawl or any third-party scraping tool — GitHub data here comes from GitHub's own structured REST API, not unstructured web pages, so a scraping tool doesn't apply (see prior discussion in this thread).
- Rewriting `RealGitHubClient` to `asyncio`/`httpx.AsyncClient` — thread-pool concurrency is the smaller, more reversible first step; an async rewrite is a bigger change not justified unless thread-pool concurrency proves insufficient.
