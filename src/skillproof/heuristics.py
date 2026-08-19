import re

_DOCS_OR_CONFIG_PATTERNS = (
    re.compile(r"\.md$", re.IGNORECASE),
    re.compile(r"\.rst$", re.IGNORECASE),
    re.compile(r"\.txt$", re.IGNORECASE),
    re.compile(r"^docs/", re.IGNORECASE),
    re.compile(r"^LICENSE$", re.IGNORECASE),
    re.compile(r"^CHANGELOG", re.IGNORECASE),
    re.compile(r"^CONTRIBUTING", re.IGNORECASE),
    re.compile(r"\.(ya?ml|toml|ini|cfg|editorconfig|gitignore|gitattributes|json)$", re.IGNORECASE),
    re.compile(r"^\.github/", re.IGNORECASE),
)

MIN_PR_COMMENT_WORDS = 10


def is_file_docs_or_config(path: str) -> bool:
    return any(pattern.search(path) for pattern in _DOCS_OR_CONFIG_PATTERNS)


def is_docs_or_config_only_commit(files: list[str]) -> bool:
    """True when every changed file is a docs/config file (or the commit touched nothing)."""
    if not files:
        return True
    return all(is_file_docs_or_config(f) for f in files)


def is_low_effort_comment(body: str) -> bool:
    word_count = len(body.split())
    return word_count < MIN_PR_COMMENT_WORDS
