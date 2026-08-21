"""Ticket 01: taxonomy scoped to code-detectable Skill Tags, each carrying a
Detection Pattern, stamped with a taxonomy_version. `taxonomy` is a pure data
module, so most of these are direct unit tests rather than going through the
HTTP seam (the HTTP-level rejection of a removed Skill Tag is covered in
test_api_flow.py) — the one exception is the `/skills` response-shape check,
which only makes sense as an HTTP-level assertion.
"""

from skillproof import taxonomy

REMOVED_PRACTICE_SKILLS = [
    "System design",
    "Security engineering",
    "Accessibility (a11y)",
    "Performance optimization",
    "Event-driven architecture",
    "Microservices architecture",
]


def test_practice_skills_with_no_detection_pattern_are_removed():
    names = {s.name for s in taxonomy.list_skills()}

    for removed in REMOVED_PRACTICE_SKILLS:
        assert removed not in names


def test_removed_skill_is_unknown():
    for removed in REMOVED_PRACTICE_SKILLS:
        assert not taxonomy.is_known_skill(removed)


def test_every_surviving_skill_tag_carries_a_nonempty_detection_pattern():
    for skill in taxonomy.list_skills():
        pattern = skill.detection_pattern
        has_any_marker = bool(
            pattern.manifest_packages or pattern.file_extensions or pattern.config_files or pattern.content_markers
        )
        assert has_any_marker, f"{skill.name} has no authored Detection Pattern"


def test_language_skill_detects_by_file_extension():
    python = taxonomy.get_skill("Python")

    assert ".py" in python.detection_pattern.file_extensions


def test_package_skill_detects_by_manifest_package():
    fastapi = taxonomy.get_skill("FastAPI")

    assert any(p.ecosystem == "pip" and p.name == "fastapi" for p in fastapi.detection_pattern.manifest_packages)


def test_taxonomy_is_stamped_with_a_version():
    assert isinstance(taxonomy.taxonomy_version(), int)
    assert taxonomy.taxonomy_version() >= 1


def test_get_skills_endpoint_response_shape_is_unchanged(client, fake_github):
    response = client.get("/skills")

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert set(body[0].keys()) == {"name", "category", "description"}
