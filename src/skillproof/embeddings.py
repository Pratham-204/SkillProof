from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from skillproof.config import get_settings


@lru_cache
def _model():
    # Imported lazily so modules that don't need embeddings (e.g. simple
    # unit tests) don't pay the sentence-transformers import cost.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model_name)


class EmbeddingsBackend(ABC):
    """What embed_batch needs to turn text into vectors — the seam a test
    substitutes to get fixed, known vectors instead of a live model's output.
    taxonomy.py's disk-cached skill-tag embeddings are bypassed while a
    non-real (i.e. FakeEmbeddingsBackend) backend is installed — see
    using_real_backend()."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray: ...

    @property
    def cache_key(self) -> str:
        """Identifies this backend + model combination. taxonomy.py's on-disk
        embeddings cache stores this alongside the cached vectors and recomputes
        whenever the active backend's cache_key no longer matches what's on disk,
        so a future backend/model swap never silently reuses vectors computed in
        a different embedding space. Not abstract: only backends that actually use
        the disk cache (see using_real_backend()) need a meaningful override —
        FakeEmbeddingsBackend never does, so it inherits this default unused."""
        return type(self).__name__


class SentenceTransformerBackend(EmbeddingsBackend):
    """The real backend: a local, free sentence-transformer model."""

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.asarray(_model().encode(texts, normalize_embeddings=False))

    @property
    def cache_key(self) -> str:
        return f"sentence-transformer:{get_settings().embedding_model_name}"


@dataclass
class FakeEmbeddingsBackend(EmbeddingsBackend):
    """Fixed vectors for known texts. Unlisted text gets a zero vector (cosine
    similarity 0 against anything), sized to match whatever's already in
    vectors_by_text so a test setting one vector never has to also pick a
    dimension. Set every vector this test needs before the first embed_batch
    call that would use them — taxonomy._embeddings_cache() is lru_cache'd, so
    a later addition to vectors_by_text won't be picked up until the next
    taxonomy._embeddings_cache.cache_clear() (the fake_embeddings fixture
    handles this for the whole-taxonomy case; per-item text has no such cache).
    """

    vectors_by_text: dict[str, np.ndarray] = field(default_factory=dict)
    default_dim: int = 8
    # Test seam for scoring's per-skill batched embeddings call: embed_batch
    # raises if any text in a given call is listed here, letting a test
    # simulate one skill's embeddings call failing without touching any
    # other skill's (each skill's matching Evidence Items are batched into
    # their own single embed_batch call).
    fail_for_texts: set[str] = field(default_factory=set)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if self.fail_for_texts.intersection(texts):
            raise RuntimeError("Simulated embeddings backend failure")
        dim = len(next(iter(self.vectors_by_text.values()))) if self.vectors_by_text else self.default_dim
        return np.asarray([self.vectors_by_text.get(text, np.zeros(dim)) for text in texts])


_backend: EmbeddingsBackend = SentenceTransformerBackend()


def set_backend(backend: EmbeddingsBackend) -> None:
    """Test seam: install a fake backend, or a fresh SentenceTransformerBackend()
    to restore the real one."""
    global _backend
    _backend = backend


def using_real_backend() -> bool:
    """True for any backend except the test-only FakeEmbeddingsBackend — i.e. any
    backend whose vectors are safe to persist to and read from taxonomy.py's disk
    cache. Deliberately not an isinstance check against one specific real backend
    class, so a future non-local backend also gets to use the disk cache."""
    return not isinstance(_backend, FakeEmbeddingsBackend)


def backend_cache_key() -> str:
    """The active backend's cache_key — what taxonomy.py's disk cache compares
    against the key stored alongside its cached vectors to detect a backend/model
    change."""
    return _backend.cache_key


def embed(text: str) -> np.ndarray:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> np.ndarray:
    return _backend.embed_batch(texts)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
