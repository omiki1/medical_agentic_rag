import hashlib
import json
import threading
from pathlib import Path


class EmbeddingService:
    """One local model instance, shared by curated and large-corpus retrieval."""

    def __init__(self, model_path, device="cpu"):
        from sentence_transformers import SentenceTransformer

        root = Path(model_path)
        identity = [
            (p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        ]
        if not identity:
            raise ValueError("Local embedding model not found")
        self.signature = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16]
        self.model = SentenceTransformer(model_path, device=device, local_files_only=True)
        self.dimension = self.model.get_embedding_dimension()
        self.lock = threading.Lock()

    def encode(self, texts, batch_size=32):
        with self.lock:
            return self.model.encode(
                texts, normalize_embeddings=True, batch_size=batch_size, show_progress_bar=False
            )
