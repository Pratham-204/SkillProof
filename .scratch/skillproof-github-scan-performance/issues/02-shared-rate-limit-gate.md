# 02 — Replace per-call blocking backoff with a shared rate-limit gate

**What to build:** `_fetch_page` (github_client.py:324-350) currently sleeps synchronously in-line whenever it detects a rate limit (`_is_rate_limited`, `_backoff_seconds`, 363-374), blocking the whole request path. Once requests run concurrently (ticket 01), that per-call sleep would let every in-flight worker independently discover the same 403 and each sleep/retry on its own. Replace it with one shared gate: the first worker to see `X-RateLimit-Remaining: 0` (or a secondary-limit response) records a "resume at" timestamp and every worker — including ones already in flight — waits on that single shared cooldown before issuing its next request, instead of each sleeping and re-triggering the same limit independently.

**Blocked by:** 01 (this only matters once requests are concurrent; can be built in parallel but should land together)

**Status:** done

- [x] A shared rate-limit gate — `threading.Lock` `_rate_limit_gate` on `RealGitHubClient` — is checked (acquired/released) by every request before it's issued, and held by whichever thread is backing off, replacing the previous per-call unguarded `time.sleep` in `_fetch_page`.
- [x] The thread that hits a secondary-rate-limit 403 holds the gate for the duration of its backoff sleep; any other thread's next request blocks acquiring the same lock until that sleep finishes, instead of each thread independently sleeping and re-requesting.
- [x] `max_retries=5` behavior is unchanged — each call still bounds its own retry attempts the same way as before.
- [x] All existing rate-limit tests (`test_get_manifest_files_retries_on_secondary_rate_limit_then_succeeds`) pass unchanged.
- [x] New test (`tests/test_real_github_client.py::test_rate_limit_gate_is_held_by_the_backing_off_thread`): asserts `_rate_limit_gate.locked()` is `True` at the exact moment the backoff sleep runs — proving the mechanism that makes other threads wait directly, rather than relying on flaky wall-clock timing between threads.

## Comments

Implemented on branch `test`. Scoped down from the original ticket text: the codebase's actual `_is_secondary_rate_limit`/`_backoff_seconds` functions only recognize `Retry-After` and secondary-rate-limit/abuse-detection response text — there is no `X-RateLimit-Remaining`/`X-RateLimit-Reset`-based primary-limit detection in `github_client.py` today (the `f8dede2` commit message referenced when this ticket was written doesn't match what's actually in the file; that primary-limit precision logic isn't present to preserve). The shared-gate mechanism this ticket delivers works identically regardless of which check trips it, so adding real primary-limit detection is separate, uncomplicated future work if it's ever wanted.
