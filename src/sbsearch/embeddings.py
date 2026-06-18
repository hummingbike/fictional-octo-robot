"""Local embedding model wrapper (F6, Phase 3).

Uses fastembed (ONNX Runtime, no torch) so semantic search stays fully
local/offline per PRD's privacy requirement, without the multi-GB torch
dependency the Phase 0 spike explicitly avoided. The default model is a
small multilingual one (Korean included, matching this project's notes),
not the English-only model PLAN.md originally sketched.
"""

from __future__ import annotations

from typing import Iterable

DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class LocalEmbedder:
    """Wraps fastembed.TextEmbedding. Instantiating loads the ONNX model."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        from fastembed import TextEmbedding  # heavy import, deferred until needed

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(list(texts))]
