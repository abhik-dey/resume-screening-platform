"""
Deterministic local embedding provider — no API key required.

WHY THIS EXISTS
---------------
Two reasons, both practical:

1. TESTS. Real embedding calls in a test suite are slow, cost money, and
   introduce network flakiness. This produces identical vectors for
   identical text, every time, instantly.

2. RUNNABILITY. Someone cloning this repo can see semantic indexing and
   search work end-to-end before signing up for any API. That matters for
   a project meant to be read and run by others.

WHAT IT IS NOT
--------------
This is NOT semantic. It hashes character n-grams into a fixed-size vector,
so texts sharing substrings land near each other, but it has no
understanding of meaning: "car" and "automobile" are unrelated to it.

That's a real limitation, stated plainly rather than glossed over. It's a
structural stand-in that exercises every code path correctly — for actual
semantic search, configure a real embedding provider.
"""
import hashlib
import math
import re

from app.domain.interfaces.embedding_provider import EmbeddingProvider

DEFAULT_DIMENSIONS = 256
_NGRAM_SIZE = 3
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        # Named explicitly so stored vectors are identifiable as non-semantic
        # — nobody should later mistake these for real embeddings.
        return "local-hash-ngram (non-semantic fallback)"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = _TOKEN_PATTERN.findall(text.lower())

        for token in tokens:
            # Whole-token feature, so exact matches weigh heavily.
            self._add_feature(vector, token, weight=2.0)
            # Character n-grams, so near-matches ("kubernetes"/"kubernete")
            # still land close together.
            padded = f" {token} "
            for i in range(len(padded) - _NGRAM_SIZE + 1):
                self._add_feature(vector, padded[i : i + _NGRAM_SIZE], weight=1.0)

        return _normalize(vector)

    def _add_feature(self, vector: list[float], feature: str, weight: float) -> None:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % self._dimensions
        # Sign bit from a different part of the digest, so colliding features
        # can cancel rather than always reinforcing each other.
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += weight * sign


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        # Empty or unusable text. A zero vector would make cosine similarity
        # undefined, so return a valid unit vector instead.
        return [1.0] + [0.0] * (len(vector) - 1)
    return [v / magnitude for v in vector]
