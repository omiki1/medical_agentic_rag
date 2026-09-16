"""Restartable, versioned vector ingestion. Run only after application validation."""

import argparse
import hashlib
import json
import sqlite3
import time

from ai.EmbeddingService import EmbeddingService
from common.Settings import Settings
from rag.BM25Retriever import tokenize

from create_data.QADocumentBuilder import QADocumentBuilder


class QAImporter:
    def __init__(self, settings, limit=1000, sample_rate=1.0):
        self.settings, self.limit = settings, limit
        self.sample_rate = sample_rate

    @staticmethod
    def checksum(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def atomic_json(path, value):
        temp = path.with_suffix(".tmp.json")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def run(self, publish=False):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        started = time.perf_counter()
        files = [
            self.settings.data_root / name
            for name in ["finetune_zh_cleaned.jsonl", "reward_zh_cleaned.jsonl"]
        ]
        if not all(path.is_file() for path in files):
            raise FileNotFoundError("DATA_ROOT must contain both cleaned finetune and reward JSONL files")
        sources = [
            {"file": path.name, "bytes": path.stat().st_size, "sha256": self.checksum(path)} for path in files
        ]
        embedding = EmbeddingService(self.settings.embedding_model, self.settings.model_device)
        spec = {
            "sources": sources,
            "embedding_signature": embedding.signature,
            "dimension": embedding.dimension,
            "limit": self.limit,
            "protocol": 3,
            "sample_rate": self.sample_rate,
            "chunk_chars": 450,
            "overlap_chars": 50,
            "collection": self.settings.collection_name,
        }
        generation = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:20]
        root = self.settings.data_dir / "qa"
        target = root / generation
        target.mkdir(parents=True, exist_ok=True)
        manifest_file = target / "manifest.json"
        if manifest_file.exists():
            report = json.loads(manifest_file.read_text(encoding="utf-8"))
            if publish:
                self.atomic_json(root / "active.json", report)
            print(json.dumps({"reused": True, **report}, ensure_ascii=False))
            return report
        # A per-generation exclusive lock prevents concurrent writers. OS releases it on exit.
        import portalocker

        with portalocker.Lock(str(target / "writer.lock"), timeout=1):
            client = chromadb.PersistentClient(
                path=str(self.settings.chroma_path / generation),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            collection = client.get_or_create_collection(
                self.settings.collection_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine", "embedding_signature": embedding.signature},
            )
            conn = sqlite3.connect(target / "index.sqlite")
            try:
                conn.executescript("""
                    PRAGMA journal_mode=WAL;
                    CREATE TABLE IF NOT EXISTS documents (id TEXT UNIQUE NOT NULL, source_id TEXT NOT NULL, body TEXT NOT NULL);
                    CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(tokens);
                    CREATE TABLE IF NOT EXISTS qa_sources (id TEXT PRIMARY KEY);
                    CREATE TABLE IF NOT EXISTS progress (key TEXT PRIMARY KEY, body TEXT NOT NULL);
                """)
                row = conn.execute("SELECT body FROM progress WHERE key='state'").fetchone()
                state = (
                    json.loads(row[0])
                    if row
                    else {
                        "file_index": 0,
                        "offset": 0,
                        "line": 0,
                        "accepted": 0,
                        "excluded_split": 0,
                        "invalid": 0,
                        "duplicates": 0,
                        "sampled_out": 0,
                    }
                )
                pending = []

                def flush():
                    if pending:
                        vectors = embedding.encode([doc.title + " " + doc.text for doc in pending])
                        collection.upsert(ids=[doc.id for doc in pending], embeddings=vectors.tolist())
                        for doc in pending:
                            result = conn.execute(
                                "INSERT OR IGNORE INTO documents VALUES (?,?,?)",
                                (doc.id, doc.source_id, doc.model_dump_json()),
                            )
                            if result.rowcount:
                                conn.execute(
                                    "INSERT INTO search(rowid,tokens) VALUES (?,?)",
                                    (result.lastrowid, " ".join(tokenize(doc.title + " " + doc.text))),
                                )
                    conn.execute("INSERT OR REPLACE INTO progress VALUES ('state',?)", (json.dumps(state),))
                    conn.commit()
                    pending.clear()

                limited = False
                while state["file_index"] < len(files):
                    path = files[state["file_index"]]
                    with path.open("rb") as stream:
                        stream.seek(state["offset"])
                        while line := stream.readline():
                            if self.limit is not None and state["accepted"] >= self.limit:
                                limited = True
                                break
                            state["line"] += 1
                            state["offset"] = stream.tell()
                            try:
                                row = json.loads(line.decode("utf-8-sig"))
                                if not isinstance(row, dict):
                                    raise ValueError("Expected JSON object")
                                sample_key = str(row.get("prompt") or row.get("question") or "")
                                sample = (
                                    int.from_bytes(hashlib.sha256(sample_key.encode()).digest()[:8], "big")
                                    / 2**64
                                )
                                if sample >= self.sample_rate:
                                    docs, outcome = [], "sampled_out"
                                else:
                                    docs, outcome = QADocumentBuilder.build(row, path.name, state["line"])
                            except (ValueError, TypeError, UnicodeError):
                                docs, outcome = [], "invalid"
                            if docs:
                                inserted = conn.execute(
                                    "INSERT OR IGNORE INTO qa_sources VALUES (?)", (docs[0].source_id,)
                                ).rowcount
                                if inserted:
                                    pending.extend(docs)
                                    state["accepted"] += 1
                                else:
                                    state["duplicates"] += 1
                            else:
                                state[outcome] += 1
                            if len(pending) >= 128 or state["line"] % 1000 == 0:
                                flush()
                                print(
                                    json.dumps(
                                        {
                                            "file": path.name,
                                            "line": state["line"],
                                            "accepted": state["accepted"],
                                            "vectors": collection.count(),
                                        },
                                        ensure_ascii=False,
                                    ),
                                    flush=True,
                                )
                    if limited:
                        break
                    state.update(file_index=state["file_index"] + 1, offset=0, line=0)
                    flush()
                flush()
                count = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                assert count == collection.count(), "Vector and text index counts diverged"
                assert count == conn.execute("SELECT count(*) FROM search").fetchone()[0], (
                    "Lexical index count diverged"
                )
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                report = {
                    **spec,
                    **state,
                    "generation": generation,
                    "documents": count,
                    "complete": not limited and state["file_index"] == len(files) and self.sample_rate == 1.0,
                    "selection_complete": not limited and state["file_index"] == len(files),
                    "duration_seconds": round(time.perf_counter() - started, 2),
                    "review_status": "unreviewed",
                }
                self.atomic_json(manifest_file, report)
                if publish:
                    self.atomic_json(root / "active.json", report)
                self.atomic_json(self.settings.reports_dir / "qa-ingestion.json", report)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return report
            finally:
                conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument(
        "--limit", type=int, default=1000, help="Number of accepted training rows, default 1000"
    )
    limits.add_argument("--all", action="store_true", help="Process the entire training partition")
    parser.add_argument(
        "--publish", action="store_true", help="Publish this version for serving after restart"
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=1.0,
        help="Deterministic question-hash sample across the input, 0 < rate <= 1",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not 0 < args.sample_rate <= 1:
        parser.error("--sample-rate must be between 0 and 1")
    QAImporter(Settings(), None if args.all else args.limit, args.sample_rate).run(args.publish)
