"""embeddings.py previously had only one adapter (the real sentence-transformer
model), so the seam was hypothetical, not real — Depth's tests could only pass
by hand-calibrating prose against the live model's actual output (see the
comments in tests/fixtures/github_fixtures.py). A second adapter,
FakeEmbeddingsBackend, makes it a real seam: tests can now pin exact vectors.

taxonomy.py's skill-tag embeddings are disk-cached (skills_embeddings.npz,
checked into the repo) — a fake backend must bypass that cache, or a test
would compare a fake evidence-item vector against a real, cached skill-tag
vector, which is meaningless. These tests prove that bypass.
"""

import numpy as np
import pytest

from skillproof import embeddings, taxonomy
from skillproof.embeddings import EmbeddingsBackend, FakeEmbeddingsBackend, SentenceTransformerBackend


class _SecondRealBackend(EmbeddingsBackend):
    """A second, deliberately non-fake, non-SentenceTransformerBackend adapter.
    Proves the disk cache generalizes to any real backend rather than being
    hardcoded to recognize one specific class — and its configurable cache_key
    lets a test simulate a backend/model swap without a live model."""

    def __init__(self, key: str, vector: list[float]):
        self._key = key
        self._vector = np.array(vector)
        self.calls = 0

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        return np.asarray([self._vector for _ in texts])

    @property
    def cache_key(self) -> str:
        return self._key


@pytest.fixture
def second_real_backend():
    """Installs a _SecondRealBackend built with the given key/vector, clearing
    taxonomy's in-memory cache so it's recomputed through the new backend.
    Restores the real backend on teardown, same as the fake_embeddings fixture."""

    def _install(key: str, vector: list[float]) -> _SecondRealBackend:
        backend = _SecondRealBackend(key=key, vector=vector)
        embeddings.set_backend(backend)
        taxonomy._embeddings_cache.cache_clear()
        return backend

    yield _install
    embeddings.set_backend(SentenceTransformerBackend())
    taxonomy._embeddings_cache.cache_clear()


def test_fake_backend_returns_its_own_fixed_vectors(fake_embeddings):
    fake_embeddings.vectors_by_text["hello"] = np.array([1.0, 0.0])

    vector = embeddings.embed("hello")

    assert list(vector) == [1.0, 0.0]


def test_installing_a_fake_backend_bypasses_taxonomys_disk_cache(fake_embeddings):
    """Without the bypass, taxonomy.skill_embedding would keep returning the
    real, disk-cached vector regardless of which backend is installed."""
    description = taxonomy.get_skill("FastAPI").description
    fake_embeddings.vectors_by_text[f"FastAPI: {description}"] = np.array([1.0, 0.0])

    vector = taxonomy.skill_embedding("FastAPI")

    assert list(vector) == [1.0, 0.0]


def test_fake_backend_never_gets_persisted_to_the_real_disk_cache(fake_embeddings, tmp_path, monkeypatch):
    fake_cache_path = tmp_path / "skills_embeddings.npz"
    monkeypatch.setattr(taxonomy, "EMBEDDINGS_CACHE_PATH", fake_cache_path)

    taxonomy.skill_embedding("FastAPI")

    assert not fake_cache_path.exists()


def test_restoring_the_real_backend_uses_the_real_disk_cache_again(fake_embeddings):
    assert embeddings.using_real_backend() is False

    embeddings.set_backend(SentenceTransformerBackend())
    taxonomy._embeddings_cache.cache_clear()

    cached = np.load(taxonomy.EMBEDDINGS_CACHE_PATH, allow_pickle=False)
    names = list(cached["names"])
    expected = cached[f"vec_{names.index('FastAPI')}"]

    vector = taxonomy.skill_embedding("FastAPI")

    # Compares against the raw on-disk file directly, proving the cache was
    # actually read rather than recomputed via either backend.
    assert np.array_equal(vector, expected)


def test_fake_backend_is_a_real_embeddings_backend_adapter():
    fake = FakeEmbeddingsBackend()
    assert isinstance(fake, embeddings.EmbeddingsBackend)


def test_disk_cache_generalizes_to_any_real_backend_and_invalidates_on_a_backend_change(
    tmp_path, monkeypatch, second_real_backend
):
    """Not just SentenceTransformerBackend: any non-fake backend reads from and
    writes to the disk cache, and the cache is only reused while the active
    backend's cache_key still matches whatever produced it — proving both the
    generalization and the invalidation-on-change behavior in one flow."""
    fake_cache_path = tmp_path / "skills_embeddings.npz"
    monkeypatch.setattr(taxonomy, "EMBEDDINGS_CACHE_PATH", fake_cache_path)

    old_backend = second_real_backend(key="old-backend:v1", vector=[1.0, 0.0])
    first = taxonomy.skill_embedding("FastAPI")
    assert list(first) == [1.0, 0.0]
    assert old_backend.calls == 1
    cached = np.load(fake_cache_path, allow_pickle=False)
    assert str(cached["backend_key"][0]) == "old-backend:v1"

    # Same backend/key again: served from disk, not recomputed.
    taxonomy._embeddings_cache.cache_clear()
    second = taxonomy.skill_embedding("FastAPI")
    assert list(second) == [1.0, 0.0]
    assert old_backend.calls == 1

    # A different backend/key: the cache is detected as stale and recomputed
    # rather than silently reusing vectors from the old embedding space.
    new_backend = second_real_backend(key="new-backend:v1", vector=[0.0, 1.0])
    third = taxonomy.skill_embedding("FastAPI")
    assert list(third) == [0.0, 1.0]
    assert new_backend.calls == 1


def test_legacy_cache_without_a_backend_key_is_still_used_by_the_real_backend(tmp_path, monkeypatch):
    """A cache written before backend_key existed (e.g. the checked-in production
    file) has no way to record which backend produced it. Treated as a match for
    today's only real backend rather than forcing an unnecessary recompute."""
    fake_cache_path = tmp_path / "skills_embeddings.npz"
    monkeypatch.setattr(taxonomy, "EMBEDDINGS_CACHE_PATH", fake_cache_path)
    names = [s.name for s in taxonomy.list_skills()]
    np.savez(fake_cache_path, names=np.array(names), **{f"vec_{i}": np.array([1.0, 0.0]) for i in range(len(names))})
    taxonomy._embeddings_cache.cache_clear()

    vector = taxonomy.skill_embedding("FastAPI")

    assert list(vector) == [1.0, 0.0]

    taxonomy._embeddings_cache.cache_clear()
