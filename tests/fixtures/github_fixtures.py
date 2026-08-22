from datetime import datetime, timedelta, timezone

from skillproof.github_client import (
    CommitRecord,
    FakeGitHubClient,
    GitHubUser,
    MergedPullRequest,
    PrCommentRecord,
    Repo,
)

# Text calibrated against the real all-MiniLM-L6-v2 model (see implementation
# notes): strongly similar to the "FastAPI" Skill Tag (>0.35), and essentially
# unrelated to "Rust" (well under 0.35), so scoring behaves deterministically
# without mocking the embedding step.
QUALIFYING_COMMIT_MESSAGE = (
    "Add FastAPI endpoint for candidate verification\n"
    "Wrote a new Python async def verify handler using FastAPI dependency injection, "
    "added pytest tests for the route, updated requirements.txt with fastapi and uvicorn."
)
QUALIFYING_REVIEW_COMMENT = (
    "This FastAPI implementation looks solid overall, but I think the exception handling "
    "around the FastAPI dependency injection could be cleaner - consider extracting the retry "
    "logic into its own helper function so the main handler stays readable and the FastAPI "
    "route tests are easier to reason about."
)
QUALIFYING_DIFF_TEXT = (
    "+from fastapi import FastAPI, Depends\n"
    "+app = FastAPI()\n"
    "+@app.post('/verify')\n"
    "+async def verify(payload: VerifyRequest):\n"
)
LOW_EFFORT_COMMENT = "LGTM, thanks!"
DOCS_ONLY_COMMIT_MESSAGE = (
    "Document the FastAPI verify endpoint usage in detail, explaining FastAPI dependency "
    "injection and FastAPI background tasks for new contributors."
)

OWNED_REPO = Repo(owner="octodev", name="skillproof-lib", fork=False)
EXTERNAL_REPO = Repo(owner="someorg", name="cool-project", fork=False)
EXTERNAL_REPO_MERGED_PR_NUMBER = 7

_NOW = datetime.now(timezone.utc)


def wire_verified_candidate(fake_github: FakeGitHubClient, *, login: str, github_user_id: int, code: str) -> None:
    """Populates a FakeGitHubClient with fixture repos/commits/PRs for one candidate.

    Evidence spans ~120 days so the temporal multiplier is 1.0, and includes
    both a docs-only commit and a low-effort PR comment so the heuristic
    filter (issue 03) has something real to exclude.
    """
    token = f"token-for-{code}"
    fake_github.tokens_by_code[code] = token
    fake_github.users_by_code[code] = GitHubUser(id=github_user_id, login=login)

    fake_github.owned_repos[login] = [OWNED_REPO]
    fake_github.merged_prs[login] = [MergedPullRequest(repo=EXTERNAL_REPO, number=EXTERNAL_REPO_MERGED_PR_NUMBER)]

    # Django is declared here but never touched by any commit below, proving
    # the declared_only path (issue 02) alongside FastAPI's fully-verified one.
    fake_github.manifest_files[OWNED_REPO.full_name] = {"requirements.txt": "Django==4.2\ngunicorn==21.2\n"}

    fake_github.commits[OWNED_REPO.full_name] = [
        CommitRecord(
            repo=OWNED_REPO,
            sha="c1",
            message=QUALIFYING_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=120),
            files=["skillproof/verify.py", "tests/test_verify.py"],
            diff_text=QUALIFYING_DIFF_TEXT,
            url=f"https://github.com/{OWNED_REPO.full_name}/commit/c1",
        ),
        CommitRecord(
            repo=OWNED_REPO,
            sha="c2-docs-only",
            message=DOCS_ONLY_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=60),
            files=["docs/verify.md", "README.md"],
            diff_text="",
            url=f"https://github.com/{OWNED_REPO.full_name}/commit/c2-docs-only",
        ),
    ]
    fake_github.pr_commits[(EXTERNAL_REPO.full_name, EXTERNAL_REPO_MERGED_PR_NUMBER)] = [
        CommitRecord(
            repo=EXTERNAL_REPO,
            sha="e1",
            message=QUALIFYING_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=10),
            files=["app/verify.py"],
            diff_text=QUALIFYING_DIFF_TEXT,
            url=f"https://github.com/{EXTERNAL_REPO.full_name}/commit/e1",
        ),
    ]
    # Author-matching but NOT part of the merged PR above: proves the
    # fork-and-fake defense (hybrid-scoring ticket 03) — a blanket author-filtered scan of
    # cool-project's history would have picked this up, PR-scoping doesn't.
    # `list_commits` is never called for external repos, so this is unreachable
    # by the real ingestion path; it's here purely as a regression trap.
    fake_github.commits[EXTERNAL_REPO.full_name] = [
        CommitRecord(
            repo=EXTERNAL_REPO,
            sha="e2-not-in-any-merged-pr",
            message=QUALIFYING_COMMIT_MESSAGE,
            date=_NOW - timedelta(days=5),
            files=["app/other.py"],
            diff_text=QUALIFYING_DIFF_TEXT,
            url=f"https://github.com/{EXTERNAL_REPO.full_name}/commit/e2-not-in-any-merged-pr",
        ),
    ]

    fake_github.pr_comments[OWNED_REPO.full_name] = [
        PrCommentRecord(
            repo=OWNED_REPO,
            comment_id=1,
            body=QUALIFYING_REVIEW_COMMENT,
            date=_NOW - timedelta(days=30),
            url=f"https://github.com/{OWNED_REPO.full_name}/pull/1#comment-1",
        ),
        PrCommentRecord(
            repo=OWNED_REPO,
            comment_id=2,
            body=LOW_EFFORT_COMMENT,
            date=_NOW - timedelta(days=30),
            url=f"https://github.com/{OWNED_REPO.full_name}/pull/1#comment-2",
        ),
    ]
