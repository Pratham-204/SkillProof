"""Direct unit tests for heuristics.py — a small, pure, dependency-free module
previously only exercised indirectly through the full connect->verify->
evidence-card HTTP flow in test_api_flow.py. A regression here used to surface
as a confusing assertion several layers up about source_commits; these test
the heuristics themselves.
"""

from skillproof import heuristics


def test_markdown_file_is_docs_or_config():
    assert heuristics.is_file_docs_or_config("README.md") is True


def test_docs_directory_file_is_docs_or_config():
    assert heuristics.is_file_docs_or_config("docs/architecture.rst") is True


def test_well_known_root_files_are_docs_or_config():
    for path in ("LICENSE", "CHANGELOG.md", "CONTRIBUTING.md"):
        assert heuristics.is_file_docs_or_config(path) is True


def test_config_extensions_are_docs_or_config():
    for path in ("pyproject.toml", "settings.yaml", "mypy.ini", ".gitignore", "tsconfig.json", "notes.txt"):
        assert heuristics.is_file_docs_or_config(path) is True


def test_github_workflow_file_is_docs_or_config():
    assert heuristics.is_file_docs_or_config(".github/workflows/ci.yml") is True


def test_source_file_is_not_docs_or_config():
    assert heuristics.is_file_docs_or_config("src/skillproof/scoring.py") is False


def test_commit_touching_nothing_is_docs_or_config_only():
    assert heuristics.is_docs_or_config_only_commit([]) is True


def test_commit_touching_only_docs_files_is_docs_or_config_only():
    assert heuristics.is_docs_or_config_only_commit(["README.md", "docs/guide.md"]) is True


def test_commit_touching_a_real_file_is_not_docs_or_config_only():
    assert heuristics.is_docs_or_config_only_commit(["README.md", "src/app.py"]) is False


def test_protected_filename_carve_out_survives_even_though_its_extension_matches_docs_pattern():
    """A Detection Pattern config file (e.g. docker-compose.yml for Docker) must
    never be filtered as noise, even though its .yml extension would otherwise
    match the docs/config patterns — this is the exact carve-out the
    architecture review found had no test exercising it at all."""
    protected = frozenset({"docker-compose.yml"})

    assert heuristics.is_docs_or_config_only_commit(["docker-compose.yml"], protected) is False
    # An unprotected file with the same extension is still correctly treated as noise.
    assert heuristics.is_docs_or_config_only_commit(["other-config.yml"], protected) is True
    # A protected file alongside real noise still makes the whole commit non-noise.
    assert heuristics.is_docs_or_config_only_commit(["README.md", "docker-compose.yml"], protected) is False


def test_matches_any_filename_is_case_insensitive_suffix_match():
    assert heuristics.matches_any_filename("infra/Docker-Compose.YML", frozenset({"docker-compose.yml"})) is True


def test_matches_any_filename_false_when_no_suffix_matches():
    assert heuristics.matches_any_filename("app/main.py", frozenset({"docker-compose.yml"})) is False


def test_comment_under_the_word_threshold_is_low_effort():
    assert heuristics.is_low_effort_comment("LGTM, thanks!") is True


def test_comment_at_exactly_the_word_threshold_is_not_low_effort():
    body = " ".join(["word"] * heuristics.MIN_PR_COMMENT_WORDS)
    assert heuristics.is_low_effort_comment(body) is False
