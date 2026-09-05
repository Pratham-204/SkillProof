# 03 — Process repos concurrently instead of one fully finishing before the next starts

**What to build:** `list_qualifying_commits` (github_client.py:125-162) and `ingest_evidence` (ingestion.py:66-104) currently walk owned repos and merged-PR repos serially — each repo's full paginated commit list plus every commit's detail must finish before the next repo starts. Move this to bounded concurrent repo processing, reusing the same shared thread pool and rate-limit gate from tickets 01/02 rather than spinning up per-repo resources, so total scan time tracks the slowest single repo rather than the sum of all repos.

**Blocked by:** 01, 02 (reuses the shared pool and rate-limit gate those tickets introduce)

**Status:** done

- [x] Owned repos and merged-PR repos are processed concurrently, not fully sequentially: `GitHubClient.list_qualifying_commits`'s per-repo work now goes through a new `_map_repos` hook (sequential by default, so `FakeGitHubClient`/tests are unaffected), which `RealGitHubClient` overrides to fan out across a dedicated `_repo_pool` (`max_workers=4`).
- [x] Each repo's own manifest lookups and commit-detail fetches (tickets 01/02) still run against the shared `_item_pool` and `_rate_limit_gate` — but via a **separate** `_repo_pool` for the repo-iteration level, not the same pool, to avoid a reentrancy deadlock (see Comments).
- [x] `ingest_evidence` (ingestion.py) also fans its manifest-fetch and PR-review-comment loops out across `all_repos` concurrently, via a local `ThreadPoolExecutor` scoped to that one call (auto-shut-down on exit) — this extends the ticket's repo-iteration concurrency to the two other per-repo loops living in the same function.
- [x] Existing pagination cap (100 pages via `Link` header) and ETag cache behavior are unchanged when repos are processed concurrently — the cache is now behind `_etag_lock` for thread-safety, but the cap/caching logic itself is untouched.
- [x] Final aggregated evidence (commits, manifests, PR review comments) is identical in content to today's serial result — futures are always gathered back in original repo/commit order, so only wall-clock ordering/timing changes, not the data or its ordering.
- [x] Existing `ingest_evidence` / `list_qualifying_commits` tests pass unchanged.
- [x] New tests: `tests/test_real_github_client.py::test_repos_are_processed_concurrently` (owned repos, via `RealGitHubClient`) and `tests/test_ingestion.py::test_ingest_evidence_fetches_manifests_across_repos_concurrently` (ingestion-level manifest fan-out) both use a peak-concurrency tracker with a real short sleep to prove overlapping in-flight work, not just correct serial results.

## Comments

Implemented on branch `test`, alongside tickets 01/02. **Deviation from the ticket's literal wording** ("reusing the same shared thread pool ... rather than spinning up per-repo resources"): using one single bounded pool for both repo-level and item-level submission would deadlock — a `_repo_pool` worker calling `_fetch_owned_commits`, which submits per-commit work back into that *same* pool and blocks on `.result()`, can starve it once every worker thread is simultaneously waiting on a queued task none of them is free to run. The fix is two pools with no cycle between them: `_repo_pool` (repo-level, `max_workers=4`) submits to and waits on `_item_pool` (item-level, `max_workers=8`), but `_item_pool`'s workers never submit back to `_repo_pool`, so there's no cycle to deadlock on. Both are still shared per `RealGitHubClient` instance (created once in `__init__`, shut down together via the new `close()` method — wired into `verify_service.run_verification`'s `finally` block), not recreated per call, which is the actual intent behind "shared" in the ticket.
