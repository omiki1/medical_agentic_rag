"""Read-only content preservation and published-index audit; no source or graph writes."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from common.Settings import PROJECT, Settings


def connect(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def digest_rows(connection, query):
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(query):
        digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def verify(vectors=False):
    settings = Settings()
    report = {"created_at": datetime.now(timezone.utc).isoformat()}
    originals = json.loads((PROJECT / "docs/original-manifest.json").read_text(encoding="utf-8"))
    changed = []
    for entry in originals:
        path = PROJECT.parent / entry["path"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            changed.append(entry["path"])
    report["original_source"] = {"files": len(originals), "changed": changed}
    assert not changed, "Original project differs from its recorded snapshot"
    with closing(connect(settings.data_dir / "knowledge.before-who.sqlite")) as before:
        with closing(connect(settings.data_dir / "knowledge.sqlite")) as after:
            for name, query in {
                "legacy": "SELECT id,source_id,entity,facet,review_status,body FROM documents WHERE review_status='unreviewed' ORDER BY id",
                "local_graph": "SELECT subject,relation,object,doc_id FROM edges ORDER BY subject,relation,object,doc_id",
            }.items():
                old, current = digest_rows(before, query), digest_rows(after, query)
                assert old == current, f"{name} content changed"
                report[name] = {**current, "unchanged": True}
            counts = dict(
                after.execute("SELECT review_status,count(*) FROM documents GROUP BY review_status")
            )
            assert sum(counts.values()) == after.execute("SELECT count(*) FROM document_search").fetchone()[0]
            report["knowledge_documents"] = counts
    manifest = json.loads((settings.data_dir / "qa/active.json").read_text(encoding="utf-8"))
    report["qa"] = {
        key: manifest[key]
        for key in ["generation", "sample_rate", "accepted", "documents", "selection_complete", "complete"]
    }
    report["qa"].update(
        enabled=settings.qa_enabled,
        serving_documents=manifest["documents"] if settings.qa_enabled else 0,
        note="旧索引物理完整性检查；停用状态下不参与检索",
    )
    with closing(connect(settings.data_dir / "qa" / manifest["generation"] / "index.sqlite")) as qa:
        for table, expected in [
            ("documents", manifest["documents"]),
            ("search", manifest["documents"]),
            ("qa_sources", manifest["accepted"]),
        ]:
            assert qa.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == expected
        assert qa.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        invalid_provenance = qa.execute(
            "SELECT count(*) FROM documents WHERE coalesce(json_extract(body,'$.review_status'),'')!='unreviewed' OR (coalesce(json_extract(body,'$.split'),'')!='train' AND json_extract(body,'$.split') NOT GLOB 'train_*') OR coalesce(json_extract(body,'$.source_line'),0) < 1"
        ).fetchone()[0]
        assert invalid_provenance == 0
        report["qa"]["text_fts_sources_consistent"] = True
        sample_ids = [
            qa.execute("SELECT id FROM documents ORDER BY rowid LIMIT 1 OFFSET ?", (offset,)).fetchone()[0]
            for offset in [0, manifest["documents"] // 2, manifest["documents"] - 1]
        ]
    if vectors:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=str(settings.chroma_path / manifest["generation"]),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_collection(manifest["collection"], embedding_function=None)
        assert collection.count() == manifest["documents"]
        stored = collection.get(ids=sample_ids, include=["embeddings"])
        assert len(stored["ids"]) == 3
        hits = collection.query(
            query_embeddings=stored["embeddings"].tolist(), n_results=5, include=["distances"]
        )
        # Repeated near-identical text may share a vector; compare distance rather than requiring unique top ID.
        assert all(min(distances) < 0.001 for distances in hits["distances"])
        report["qa"]["vector_count_and_query_passed"] = True
    from neo4j import READ_ACCESS, GraphDatabase

    with GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
    ) as driver:
        with driver.session(database=settings.neo4j_database, default_access_mode=READ_ACCESS) as session:
            count = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            assert count == 383229, "Neo4j relationship count changed since the baseline"
            report["neo4j"] = {"relationships": count, "writes": 0}
    (settings.reports_dir / "data-integrity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vectors", action="store_true", help="Also open Chroma and test sampled self-neighbor queries"
    )
    verify(parser.parse_args().vectors)
