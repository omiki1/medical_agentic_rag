import json
import sqlite3
from contextlib import contextmanager

from rag.BM25Retriever import tokenize
from rag.entity.Evidence import Document, Evidence
from rag.fusion.EvidenceFusion import fuse


class QARetriever:
    """Disk-backed BM25/Chroma. Only an explicitly published version is visible."""

    def __init__(self, settings, embedding=None):
        self.embedding, self.collection, self.manifest = embedding, None, {}
        self.warnings = []
        self.path = None
        if not getattr(settings, "qa_enabled", False):
            return
        pointer = settings.data_dir / "qa" / "active.json"
        if not pointer.exists():
            return
        try:
            self.manifest = json.loads(pointer.read_text(encoding="utf-8"))
            generation = self.manifest["generation"]
            if not generation.isalnum():
                raise ValueError("Invalid index generation")
            self.path = settings.data_dir / "qa" / generation / "index.sqlite"
            if not self.path.is_file():
                raise ValueError("QA text index is missing")
            if embedding and embedding.signature == self.manifest["embedding_signature"]:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                self.client = chromadb.PersistentClient(
                    path=str(settings.chroma_path / generation),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self.collection = self.client.get_collection(
                    self.manifest["collection"], embedding_function=None
                )
                if self.collection.count() != self.manifest["documents"]:
                    raise ValueError("Published vector/text count mismatch")
            elif embedding:
                self.warnings.append("QA embedding identity changed; lexical retrieval remains available")
        except Exception as error:
            self.collection = None
            self.warnings.append("QA index unavailable: " + type(error).__name__)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
        try:
            yield conn
        finally:
            conn.close()

    def document(self, doc_id):
        if not self.path or not self.path.exists():
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM documents WHERE id=?", (doc_id,)).fetchone()
        return Document.model_validate_json(row[0]) if row else None

    @staticmethod
    def expression(query):
        return " OR ".join('"' + token + '"' for token in dict.fromkeys(tokenize(query)))

    def lexical(self, query, k=12):
        expression = self.expression(query)
        if not self.path or not self.path.exists() or not expression:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT d.body,bm25(search) FROM search JOIN documents d ON d.rowid=search.rowid "
                "WHERE search MATCH ? ORDER BY bm25(search) LIMIT ?",
                (expression, k),
            ).fetchall()
        return [
            Evidence(
                document=Document.model_validate_json(body),
                methods=["qa_bm25"],
                raw_scores={"qa_bm25": -score},
            )
            for body, score in rows
        ]

    def search(self, query, k=12):
        lexical = self.lexical(query, k)
        dense = []
        if self.collection:
            vector = self.embedding.encode([query])[0].tolist()
            hits = self.collection.query(
                query_embeddings=[vector], n_results=min(k, self.manifest["documents"]), include=["distances"]
            )
            for doc_id, distance in zip(hits["ids"][0], hits["distances"][0]):
                document = self.document(doc_id)
                if document:
                    dense.append(
                        Evidence(
                            document=document, methods=["qa_dense"], raw_scores={"qa_cosine": 1 - distance}
                        )
                    )
        return fuse(lexical, dense, k=k)

    def discover(self, query, limit, offset):
        if not self.path or not self.path.exists():
            return [], 0
        expression = self.expression(query)
        with self.connect() as conn:
            if expression:
                count = conn.execute(
                    "SELECT count(*) FROM search WHERE search MATCH ?", (expression,)
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT d.body FROM search JOIN documents d ON d.rowid=search.rowid "
                    "WHERE search MATCH ? ORDER BY bm25(search) LIMIT ? OFFSET ?",
                    (expression, limit, offset),
                ).fetchall()
            else:
                count = self.manifest["documents"]
                rows = conn.execute(
                    "SELECT body FROM documents ORDER BY rowid LIMIT ? OFFSET ?", (limit, offset)
                ).fetchall()
        return [Document.model_validate_json(row[0]) for row in rows], count
