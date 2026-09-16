import hashlib
import json
import threading
from pathlib import Path

from ai.EmbeddingService import EmbeddingService

from rag.entity.Evidence import Evidence


class VectorRetriever:
    """Optional real sentence embeddings; never silently replace dense with lexical vectors."""

    def __init__(self, documents, model_path: str, cache_dir: Path, device="cpu", embedding=None):
        import numpy as np

        self.np = np
        self.documents = documents
        self.lock = threading.Lock()
        # Allow callers to share one EmbeddingService across several VectorRetriever
        # instances (e.g. authoritative-reviewed index + full-corpus exploration index)
        # so a second model copy is never loaded into GPU memory.
        self.embedding = embedding or EmbeddingService(model_path, device)
        self.model = self.embedding.model
        # Include model configuration/weights identity and ordered content in cache key.
        self.signature = self.embedding.signature
        key = hashlib.sha256(
            (
                self.signature + json.dumps([(d.id, d.title, d.text) for d in documents], ensure_ascii=False)
            ).encode()
        ).hexdigest()[:20]
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = cache_dir / f"dense-{key}.npy"
        if cache.exists():
            self.vectors = np.load(cache, allow_pickle=False)
        else:
            self.vectors = self.embedding.encode([d.title + " " + d.text for d in documents])
            with cache.open("wb") as stream:
                np.save(stream, self.vectors, allow_pickle=False)
        if self.vectors.shape[0] != len(documents):
            raise ValueError("Embedding index/document identity mismatch")

    def search(self, query, k=16, method="dense"):
        vector = self.embedding.encode([query])[0]
        scores = self.vectors @ vector
        indexes = self.np.argsort(-scores, kind="stable")[:k]
        return [
            Evidence(
                document=self.documents[int(i)],
                methods=[method],
                raw_scores={method + "_cosine": float(scores[i])},
            )
            for i in indexes
            if scores[i] > 0
        ]
