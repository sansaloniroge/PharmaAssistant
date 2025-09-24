# Stub minimal para el cliente OpenAI v1 compatible con mypy
from typing import Any, Sequence

class EmbeddingData:
    embedding: Sequence[float]

class EmbeddingsResponse:
    data: Sequence[EmbeddingData]

class Embeddings:
    def create(self, *, model: str, input: Any) -> EmbeddingsResponse: ...

class OpenAI:
    def __init__(self, *args, **kwargs) -> None: ...
    embeddings: Embeddings
