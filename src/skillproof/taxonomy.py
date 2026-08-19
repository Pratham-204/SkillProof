import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from skillproof import embeddings

DATA_DIR = Path(__file__).parent / "data"
SKILLS_PATH = DATA_DIR / "skills.json"
EMBEDDINGS_CACHE_PATH = DATA_DIR / "skills_embeddings.npz"


@dataclass(frozen=True)
class SkillTag:
    name: str
    category: str
    description: str


class UnknownSkillTagError(ValueError):
    def __init__(self, skill: str):
        super().__init__(f"'{skill}' is not a recognized Skill Tag")
        self.skill = skill


@lru_cache
def _raw_skills() -> list[SkillTag]:
    entries = json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
    return [SkillTag(name=e["name"], category=e["category"], description=e["description"]) for e in entries]


def list_skills() -> list[SkillTag]:
    return _raw_skills()


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
