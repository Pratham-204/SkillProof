"""Ticket 01: taxonomy scoped to code-detectable Skill Tags, each carrying a
Detection Pattern, stamped with a taxonomy_version. `taxonomy` is a pure data
module, so most of these are direct unit tests rather than going through the
HTTP seam (the HTTP-level rejection of a removed Skill Tag is covered in
test_api_flow.py) — the one exception is the `/skills` response-shape check,
which only makes sense as an HTTP-level assertion.
"""

import json
import os
import threading
import time

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


def test_reads_reload_after_the_taxonomy_file_changes_on_disk(isolated_taxonomy_file):
    """Simulates the nightly `taxonomy_growth` batch job — a separate OS process —
    rewriting `SKILLS_PATH` while this process already has it cached in memory.
    A real external process has no way to call this process's `_invalidate_caches`,
    so the cache must notice the file itself changed."""
    assert taxonomy.is_known_skill("ExternallyPublishedWidget") is False  # populates the cache

    data = json.loads(isolated_taxonomy_file.read_text(encoding="utf-8"))
    data["skills"].append(
        {
            "name": "ExternallyPublishedWidget",
            "category": "tool",
            "description": "x",
            "detection": {"manifest_packages": [], "file_extensions": [], "config_files": [], "content_markers": []},
        }
    )
    data["version"] += 1
    isolated_taxonomy_file.write_text(json.dumps(data), encoding="utf-8")
    bumped_mtime = isolated_taxonomy_file.stat().st_mtime + 2
    os.utime(isolated_taxonomy_file, (bumped_mtime, bumped_mtime))

    assert taxonomy.is_known_skill("ExternallyPublishedWidget") is True


def test_append_skill_tags_survives_two_concurrent_writers(isolated_taxonomy_file, monkeypatch):
    """Two overlapping `publish_new_skill_tags` runs (a cron overrun, or a manual
    rerun mid-cron — round 8, ADR-0008) must not let the second writer's
    read-modify-write silently discard the first writer's already-published entry."""
    original_loads = json.loads

    def slow_loads(*args, **kwargs):
        result = original_loads(*args, **kwargs)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(json, "loads", slow_loads)
    original_version = taxonomy.taxonomy_version()
    barrier = threading.Barrier(2)

    def publish(name: str) -> None:
        barrier.wait(timeout=5)
        taxonomy.append_skill_tags([taxonomy.SkillTag(name=name, category="tool", description="x")])

    threads = [threading.Thread(target=publish, args=(name,)) for name in ("ConcurrentWidgetA", "ConcurrentWidgetB")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert taxonomy.is_known_skill("ConcurrentWidgetA")
    assert taxonomy.is_known_skill("ConcurrentWidgetB")
    assert taxonomy.taxonomy_version() == original_version + 2
