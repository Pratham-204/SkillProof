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

from skillproof import embeddings, taxonomy
from skillproof.embeddings import FakeEmbeddingsBackend, SentenceTransformerBackend


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
