# Private-repo evidence counts toward the score but is redacted on the public card

Private repos were previously invisible to `/verify` entirely — `list_owned_public_repos` called the public-profile `/users/{login}/repos` endpoint, which cannot return a private repo for any token, and `github_oauth_scope` (`read:user`) didn't request repo content access at all. We decided to make private repos count: the scope now includes `repo` (the only classic GitHub OAuth scope that reads private repo content, and it nominally grants write access this app never exercises), and `list_owned_repos` (renamed) calls the authenticated `/user/repos` endpoint instead, falling back to the old public-only endpoint when the authenticated call fails — which is what happens for a Candidate whose token predates this change and hasn't reconnected, so nothing breaks for them.

The harder decision was what a public Evidence Card shows for private-repo evidence, since the card is reachable by anyone with the URL (Evidence Card term) — no login, no ownership check.

## Considered Options

- **Show it plainly** (repo name, commit link, same as public evidence) — rejected: a Recruiter who gets a Candidate's card URL would gain visibility into that Candidate's private code, not just their public profile. That's a real trust violation the Candidate never explicitly agreed to when sharing an Evidence Card link.
- **Count it but never surface it** (folds into the score with no trace on the card) — rejected: the whole product is built on a card being able to say *why* a score is what it is; an invisible contribution to the score is a step back from "here's the receipts," and someone comparing a claimed skill to the visible evidence would have no idea part of it isn't shown at all.
- **Count it and show that it exists, but redact which repo** (chosen) — `source_commits` replaces `repo`/`url` with a fixed placeholder ("a private repository" / empty) for a private item, and adds `private: true` so the UI renders it distinctly ("commit in a private repository") instead of a broken link. The score reflects real work; the card names the *category* of evidence without exposing the repo itself.

## Consequences

A Recruiter (or anyone else) can no longer independently verify a private-repo commit the way they can a public one — they see that it exists and contributed to the score, not what it says. That's an intentional, permanent limit on this feature's verifiability, not a gap to close later: closing it means showing someone else the Candidate's private code, which is the exact outcome the redaction exists to prevent.

Scope is also deliberately narrower than "everything the token can see": only repos the Candidate owns gain private visibility. External (non-owned) repos, reached via `list_merged_prs` for Volume's PR-membership scoping (ADR-0004), are untouched — a private repo the Candidate merely contributed to belongs to someone else, whose consent this app has no way to obtain, so extending private evidence there is out of scope for this decision.
