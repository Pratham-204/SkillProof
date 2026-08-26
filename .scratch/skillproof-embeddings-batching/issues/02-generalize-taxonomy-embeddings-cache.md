# 02 — Generalize the taxonomy embeddings disk cache beyond one backend class

**What to build:** The Skill Tag description embeddings' disk cache is currently only read from and written to when the active embeddings backend is specifically the local `SentenceTransformerBackend` class (`embeddings.using_real_backend()` is an `isinstance` check against that one class). Generalize this so any real (non-test-fake) backend can use the disk cache, with the cache detecting and invalidating itself when the active backend/model actually changes — so a future backend swap doesn't silently re-embed the whole taxonomy on every process restart, and never silently reuses a stale cache computed under a different embedding space.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] The taxonomy's Skill Tag description embeddings disk cache is read from and written to for any real embeddings backend, not only `SentenceTransformerBackend` specifically.
- [x] The cache detects when the active backend/model differs from whatever produced the on-disk cache, and invalidates (recomputes) rather than silently returning vectors computed under a different embedding space.
- [x] The existing behavior for the test-only fake backend is unchanged: it still never reads from or writes to the real on-disk cache (`tests/test_embeddings.py`'s existing bypass tests keep passing as-is).
- [x] The existing behavior for the current local `SentenceTransformerBackend` is unchanged when it's the only backend ever installed in a given process — this generalization changes nothing observable for today's only real backend.
- [x] Covered by: extending the existing `tests/test_embeddings.py` seam with a case proving cache invalidation on a backend/model change, alongside the existing bypass/restore tests.
