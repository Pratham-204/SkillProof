# 03 — Anti-gaming: PR-verified Volume + Depth commit-message discount

**What to build:** Close the two gaming surfaces the core formula leaves open — a candidate can't inflate Volume by forking a large repo, and can't inflate Depth by writing an elaborate commit message on a trivial change.

**Blocked by:** 02

**Status:** done

- [x] For external (non-owned) repos, Volume counts only commits that belong to a PR the Candidate actually opened and had merged in that repo — fetched per merged PR, not via a blanket author-filtered scan of the repo's full commit history.
- [x] A commit authored by the Candidate in an external repo, but not part of any of the Candidate's merged PRs there, does not count toward Volume.
- [x] Owned, non-fork repos are unaffected by this change — Volume there still counts all of the Candidate's own commits touching matched files, as in ticket 02.
- [x] A commit message's cosine similarity is multiplied by a fixed 0.6 discount before entering Depth's `top_3` selection; a PR review comment's similarity is unaffected.
- [x] A fixture demonstrates the discount changing the outcome: a commit message and a PR comment of equivalent topical content produce different contributions to Depth, with the commit message counting for less.
