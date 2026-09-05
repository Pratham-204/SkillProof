# 01 — Parallelize manifest probing and per-commit detail fetch

**What to build:** Introduce a shared, bounded `ThreadPoolExecutor` in `RealGitHubClient` and use it in two places that currently do sequential N+1 HTTP calls: `get_manifest_files` (github_client.py:285-297), which checks ~20 manifest filenames one at a time per repo, and the commit-detail fetch inside `_fetch_owned_commits`/`_fetch_pr_commits` (via `_commit_record`, 236-269), which currently fetches one commit's diff per call in a serial list comprehension. Both should submit all their requests to the pool and gather results, preserving today's exact return shape and ordering.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `RealGitHubClient` owns one shared `ThreadPoolExecutor` (`_item_pool`, `max_workers=8`) used by both call sites below, not a pool created per call.
- [x] `get_manifest_files` submits all manifest-filename lookups concurrently and returns the same shape as today (which manifests exist for the repo).
- [x] `_fetch_owned_commits` and `_fetch_pr_commits` submit each commit's `_commit_record` call to the pool (via a shared `_commit_records` helper) instead of a serial list comprehension, then reassemble results in the original commit order before returning — order is preserved because futures are built and gathered in `shas` order.
- [x] `httpx.Client` usage is confirmed safe for concurrent calls from multiple pool threads against the one shared client instance already held by `RealGitHubClient` (httpx documents `Client` as thread-safe for concurrent requests).
- [x] All existing tests covering `get_manifest_files`, `_fetch_owned_commits`, `_fetch_pr_commits`, and downstream ingestion/scoring pass unchanged.
- [x] New tests (`tests/test_real_github_client.py`): `test_get_manifest_files_checks_filenames_concurrently` and `test_commit_detail_fetch_runs_concurrently` use a `httpx.MockTransport` handler with a short real sleep and a peak-concurrency tracker, proving requests actually overlap in flight rather than running one at a time.

## Comments

Implemented on branch `test`. `_item_pool` is deliberately a separate pool from the new `_repo_pool` (ticket 03) — a repo-level task calling back into `_commit_records`/`get_manifest_files` and waiting on `_item_pool` from inside `_repo_pool`'s own worker thread would deadlock if both used the same bounded pool. See ticket 03's comments for the fuller rationale.
