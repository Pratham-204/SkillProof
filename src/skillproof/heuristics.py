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

MIN_PR_COMMENT_WORDS = 5


def is_file_docs_or_config(path: str) -> bool:
    return any(pattern.search(path) for pattern in _DOCS_OR_CONFIG_PATTERNS)


def is_docs_or_config_only_commit(files: list[str], protected_filenames: frozenset[str] = frozenset()) -> bool:
    """True when every changed file is docs/config noise (or the commit touched nothing).

    A file that is itself a registered Detection Pattern for some Skill Tag
    (e.g. `docker-compose.yml` for Docker) is never noise, even when its
    extension would otherwise match the docs/config patterns below — it's
    exactly the evidence Presence/Volume need to see.
    """
    if not files:
        return True
    return all(_is_noise(f, protected_filenames) for f in files)


def _is_noise(path: str, protected_filenames: frozenset[str]) -> bool:
    if _is_protected(path, protected_filenames):
        return False
    return is_file_docs_or_config(path)


def _is_protected(path: str, protected_filenames: frozenset[str]) -> bool:
    return matches_any_filename(path, protected_filenames)


def matches_any_filename(path: str, filenames: frozenset[str] | tuple[str, ...]) -> bool:
    """True when `path` ends with one of `filenames` — the one place both the
    docs/config-only commit filter and scoring's Detection Pattern file/config
    matching decide whether a path is 'the same file', so they can't quietly diverge."""
    lower = path.lower()
    return any(lower.endswith(name.lower()) for name in filenames)


def is_low_effort_comment(body: str) -> bool:
    word_count = len(body.split())
    return word_count < MIN_PR_COMMENT_WORDS
