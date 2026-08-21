import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from skillproof import embeddings

DATA_DIR = Path(__file__).parent / "data"
SKILLS_PATH = DATA_DIR / "skills.json"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "skills_embeddings.npz"


@dataclass(frozen=True)
class ManifestPackage:
    ecosystem: str
    name: str


@dataclass(frozen=True)
class DetectionPattern:
    """A Skill Tag's fingerprint for automatic identification in a Candidate's repos.

    Drives the Presence and Volume Signals (see CONTEXT.md). Every field is a list of
    independent alternatives, not an all-must-match set: any single match is a hit.
    """

    manifest_packages: tuple[ManifestPackage, ...] = ()
    file_extensions: tuple[str, ...] = ()
    config_files: tuple[str, ...] = ()
    content_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillTag:
    name: str
    category: str
    description: str
    detection_pattern: DetectionPattern = field(default_factory=DetectionPattern)


class UnknownSkillTagError(ValueError):
    def __init__(self, skill: str):
        super().__init__(f"'{skill}' is not a recognized Skill Tag")
        self.skill = skill


@lru_cache
def _taxonomy_file() -> dict:
    return json.loads(SKILLS_PATH.read_text(encoding="utf-8"))


def taxonomy_version() -> int:
    """The version stamp a re-verification compares an Evidence Card's own
    `taxonomy_version` against, to decide overwrite-in-place vs fork (ADR-0005)."""
    return _taxonomy_file()["version"]


def _parse_detection_pattern(raw: dict) -> DetectionPattern:
    return DetectionPattern(
        manifest_packages=tuple(
            ManifestPackage(ecosystem=p["ecosystem"], name=p["name"]) for p in raw.get("manifest_packages", [])
        ),
        file_extensions=tuple(raw.get("file_extensions", [])),
        config_files=tuple(raw.get("config_files", [])),
        content_markers=tuple(raw.get("content_markers", [])),
    )


@lru_cache
def _raw_skills() -> list[SkillTag]:
    entries = _taxonomy_file()["skills"]
    return [
        SkillTag(
            name=e["name"],
            category=e["category"],
            description=e["description"],
            detection_pattern=_parse_detection_pattern(e.get("detection", {})),
        )
        for e in entries
    ]


def list_skills() -> list[SkillTag]:
    return _raw_skills()


@lru_cache
def all_detection_pattern_config_files() -> frozenset[str]:
    """The union of every Skill Tag's config-file Detection Pattern entries.

    Used by ingestion to stop the docs/config-only commit filter from
    discarding a file that is itself Detection Pattern evidence for *some*
    Skill Tag (e.g. `docker-compose.yml` for Docker), even when that file's
    extension would otherwise read as pure config noise.
    """
    return frozenset(cf for skill in _raw_skills() for cf in skill.detection_pattern.config_files)


def is_known_skill(name: str) -> bool:
    return name in _skill_index()


@lru_cache
def _skill_index() -> dict[str, SkillTag]:
    return {s.name: s for s in _raw_skills()}


def get_skill(name: str) -> SkillTag:
    tag = _skill_index().get(name)
    if tag is None:
        raise UnknownSkillTagError(name)
    return tag


@lru_cache
def _embeddings_cache() -> dict[str, np.ndarray]:
    """Skill Tag embeddings, computed once locally and cached to disk.

    Recomputing per-request would be wasteful; a stale cache (taxonomy
    edited since the cache was written) is detected by comparing the
    cached skill names against the current taxonomy and recomputed.
    """
    skills = _raw_skills()
    names = [s.name for s in skills]

    if EMBEDDINGS_CACHE_PATH.exists():
        cached = np.load(EMBEDDINGS_CACHE_PATH, allow_pickle=False)
        cached_names = list(cached["names"])
        if cached_names == names:
            return {name: cached[f"vec_{i}"] for i, name in enumerate(names)}

    vectors = embeddings.embed_batch([f"{s.name}: {s.description}" for s in skills])
    save_kwargs = {f"vec_{i}": vectors[i] for i in range(len(names))}
    np.savez(EMBEDDINGS_CACHE_PATH, names=np.array(names), **save_kwargs)
    return dict(zip(names, vectors))


def skill_embedding(name: str) -> np.ndarray:
    get_skill(name)  # raises UnknownSkillTagError if not in the taxonomy
    return _embeddings_cache()[name]
