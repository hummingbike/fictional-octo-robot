"""Real integration test for the chosen embedding model (no mocking the ONNX
model itself -- this is the one place we want to catch a bad model/runtime
choice, mirroring how test_watch_latency.py exercises real FSEvents rather
than a fake watcher)."""

import math

from sbsearch.embeddings import EMBEDDING_DIM, LocalEmbedder


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def test_embed_returns_vectors_of_expected_dimension():
    embedder = LocalEmbedder()

    vectors = embedder.embed(["오늘 회의에서 예산안을 논의했다"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


def test_korean_semantic_similarity_ranks_related_text_higher():
    embedder = LocalEmbedder()
    query = "오늘 회의에서 예산안을 논의했다"
    related = "이번 분기 예산 계획을 검토했다"
    unrelated = "점심으로 김치찌개를 먹었다"

    query_vec, related_vec, unrelated_vec = embedder.embed([query, related, unrelated])

    assert _cosine_similarity(query_vec, related_vec) > _cosine_similarity(
        query_vec, unrelated_vec
    )
