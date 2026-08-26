import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from skillproof import embeddings

DATA_DIR = Path(__file__).parent / "data"
SKILLS_PATH = DATA_DIR / "skills.json"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "skills_embeddings.npz"

# The taxonomy's fixed category set. The self-extending taxonomy's LLM draft step is
# constrained to these — it cannot mint a new category (round 8, ADR-0008).
CATEGORIES = frozenset({"language", "framework", "infra", "datastore", "tool"})


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


@lru_cache
def known_manifest_package_names() -> frozenset[ManifestPackage]:
    """(ecosystem, lowercased package name) pairs already covered by some Skill
    Tag's Detection Pattern. `sightings.record_sightings` diffs a repo's declared
    packages against this to find genuinely unrecognized ones (round 8, ADR-0008)."""
    return frozenset(
        ManifestPackage(ecosystem=pkg.ecosystem, name=pkg.name.lower())
        for skill in _raw_skills()
        for pkg in skill.detection_pattern.manifest_packages
    )


def _serialize_skill_tag(skill: SkillTag) -> dict:
    """The inverse of `_parse_detection_pattern` — the one place that knows how a
    `SkillTag` maps back onto a `skills.json` record, so the on-disk shape has a
    single reader and a single writer rather than two independently-maintained ones."""
    pattern = skill.detection_pattern
    return {
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "detection": {
            "manifest_packages": [{"ecosystem": p.ecosystem, "name": p.name} for p in pattern.manifest_packages],
            "file_extensions": list(pattern.file_extensions),
            "config_files": list(pattern.config_files),
            "content_markers": list(pattern.content_markers),
        },
    }


def append_skill_tags(skills: list[SkillTag]) -> None:
    """Appends new Skill Tags and bumps `version` once, in a single file write —
    `taxonomy_growth`'s batch publish job calls this at most once per run, after
    every entry it's publishing this run has cleared every guard (round 8,
    ADR-0008). Clears every taxonomy cache afterward so the new entries (and their
    embeddings, via the existing self-healing `_embeddings_cache`) are visible
    immediately within this process. A separately running app process still needs
    its own restart to see them — same as any other taxonomy edit today;
    `_taxonomy_file` has no cross-process invalidation."""
    data = json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
    data["skills"].extend(_serialize_skill_tag(s) for s in skills)
    data["version"] += 1
    SKILLS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _invalidate_caches()


def _invalidate_caches() -> None:
    _taxonomy_file.cache_clear()
    _raw_skills.cache_clear()
    _skill_index.cache_clear()
    all_detection_pattern_config_files.cache_clear()
    known_manifest_package_names.cache_clear()
    _embeddings_cache.cache_clear()


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


def _cache_matches_active_backend(cached: np.lib.npyio.NpzFile) -> bool:
    """True if the on-disk cache was produced by whatever backend/model is active
    now. A cache written before this key existed has no "backend_key" entry at
    all — that's a pre-existing checked-in cache from the only real backend this
    codebase has ever had (SentenceTransformerBackend), so it's treated as a
    match rather than forced to recompute on every process this ships to."""
    if "backend_key" not in cached.files:
        return True
    return str(cached["backend_key"][0]) == embeddings.backend_cache_key()


@lru_cache
def _embeddings_cache() -> dict[str, np.ndarray]:
    """Skill Tag embeddings, computed once locally and cached to disk.

    Recomputing per-request would be wasteful; a stale cache is detected and
    recomputed in two independent ways: the taxonomy was edited since the cache
    was written (cached skill names no longer match), or the active embeddings
    backend/model no longer matches whatever produced the cache (see
    _cache_matches_active_backend) — guarding against silently reusing vectors
    computed in a different embedding space after a future backend swap.

    The disk cache holds real-model vectors only — both reading and writing it
    are skipped whenever a non-real embeddings backend is installed, so a test
    backend's vectors never leak into the checked-in cache file.
    """
    skills = _raw_skills()
    names = [s.name for s in skills]

    if embeddings.using_real_backend() and EMBEDDINGS_CACHE_PATH.exists():
        cached = np.load(EMBEDDINGS_CACHE_PATH, allow_pickle=False)
        cached_names = list(cached["names"])
        if cached_names == names and _cache_matches_active_backend(cached):
            return {name: cached[f"vec_{i}"] for i, name in enumerate(names)}

    vectors = embeddings.embed_batch([f"{s.name}: {s.description}" for s in skills])
    if embeddings.using_real_backend():
        save_kwargs = {f"vec_{i}": vectors[i] for i in range(len(names))}
        np.savez(
            EMBEDDINGS_CACHE_PATH,
            names=np.array(names),
            backend_key=np.array([embeddings.backend_cache_key()]),
            **save_kwargs,
        )
    return dict(zip(names, vectors))


def skill_embedding(name: str) -> np.ndarray:
    get_skill(name)  # raises UnknownSkillTagError if not in the taxonomy
    return _embeddings_cache()[name]
