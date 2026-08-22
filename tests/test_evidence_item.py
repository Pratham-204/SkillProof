"""Deepening: EvidenceItem's per-kind meaning (what "matches a Detection
Pattern" means for a commit vs. a PR comment, and which kind's text is
self-authored and therefore Depth-discountable) used to require a reader to
reconstruct it by reading ingestion.py, heuristics.py, and scoring.py
together. EvidenceItem now carries that behavior itself, at one seam.
"""

from datetime import datetime, timezone

from skillproof.ingestion import EvidenceItem
from skillproof.taxonomy import DetectionPattern, ManifestPackage

_NOW = datetime.now(timezone.utc)


def _commit(**overrides) -> EvidenceItem:
    defaults = dict(
        kind="commit",
        repo="octodev/skillproof-lib",
        ref="c1",
        url="https://example.com/c1",
        text="irrelevant prose",
        date=_NOW,
    )
    return EvidenceItem(**{**defaults, **overrides})


def _comment(**overrides) -> EvidenceItem:
    defaults = dict(
        kind="pr_comment",
        repo="octodev/skillproof-lib",
        ref="p1",
        url="https://example.com/p1",
        text="irrelevant prose",
        date=_NOW,
    )
    return EvidenceItem(**{**defaults, **overrides})


def test_commit_matches_via_changed_file_extension():
    pattern = DetectionPattern(file_extensions=(".py",))
    item = _commit(files=("app/main.py",))

    assert item.matches(pattern) is True


def test_commit_matches_via_diff_content_marker():
    pattern = DetectionPattern(content_markers=("fastapi",))
    item = _commit(diff_text="+from fastapi import FastAPI")

    assert item.matches(pattern) is True


def test_commit_message_alone_never_matches():
    """A commit message is candidate-authored prose, not evidence of code
    touched — only files/diff_text can make a commit match."""
    pattern = DetectionPattern(content_markers=("fastapi",))
    item = _commit(text="uses fastapi", files=("README.md",), diff_text="+# bump version")

    assert item.matches(pattern) is False


def test_comment_matches_via_its_text():
    pattern = DetectionPattern(manifest_packages=(ManifestPackage(ecosystem="pip", name="fastapi"),))
    item = _comment(text="This fastapi handler looks solid.")

    assert item.matches(pattern) is True


def test_comment_with_no_matching_text_does_not_match():
    pattern = DetectionPattern(content_markers=("fastapi",))
    item = _comment(text="LGTM, thanks!")

    assert item.matches(pattern) is False


def test_commit_is_self_authored():
    assert _commit().is_self_authored is True


def test_comment_is_not_self_authored():
    assert _comment().is_self_authored is False
