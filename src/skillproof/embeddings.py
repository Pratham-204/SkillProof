from functools import lru_cache

import numpy as np

from skillproof.config import get_settings


@lru_cache
def _model():
    # Imported lazily so modules that don't need embeddings (e.g. simple
    # unit tests) don't pay the sentence-transformers import cost.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model_name)


def embed(text: str) -> np.ndarray:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> np.ndarray:
    return np.asarray(_model().encode(texts, normalize_embeddings=False))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
