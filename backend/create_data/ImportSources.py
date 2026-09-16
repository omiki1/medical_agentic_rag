"""Append explicitly reviewed source summaries without rebuilding existing data."""

import hashlib
import json
import sqlite3
from urllib.parse import urlparse

from common.Settings import Settings
from rag.BM25Retriever import tokenize
from rag.entity.Evidence import Document


class SourceImporter:
    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def records(root):
        for name in ["curated_support.jsonl", "quality_support.jsonl"]:
            path = root / name
            if not path.exists():
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                raw = json.loads(line)
                raw.update(source_file=name, source_line=line_number)
                yield raw

    def run(self):
        root = self.settings.data_dir
        destination, staging = root / "knowledge.sqlite", root / "knowledge.sources.sqlite"
        source = sqlite3.connect(destination)
        conn = sqlite3.connect(staging)
        source.backup(conn)
        source.close()
        added = 0
        try:
            for raw in self.records(root):
                document = Document.model_validate(raw)
                if urlparse(document.source_url).hostname not in {
                    "www.nhs.uk",
                    "www.niddk.nih.gov",
                    "www.who.int",
                }:
                    raise ValueError("Source is outside the reviewed public-health allowlist")
                previous = conn.execute("SELECT body FROM documents WHERE id=?", (document.id,)).fetchone()
                if previous:
                    if previous[0] != document.model_dump_json():
                        raise ValueError("Existing source ID has different content; create a new version")
                    continue
                cursor = conn.execute(
                    "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                    (
                        document.id,
                        document.source_id,
                        document.entity,
                        document.facet,
                        document.review_status,
                        document.model_dump_json(),
                    ),
                )
                conn.execute(
                    "INSERT INTO document_search(rowid,tokens) VALUES (?,?)",
                    (cursor.lastrowid, " ".join(tokenize(document.title + " " + document.text))),
                )
                added += 1
            manifest = json.loads(
                conn.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0]
            )
            counts = dict(conn.execute("SELECT review_status,count(*) FROM documents GROUP BY review_status"))
            digest = hashlib.sha256()
            for (body,) in conn.execute("SELECT body FROM documents ORDER BY id"):
                digest.update(body.encode())
            manifest.update(
                documents=sum(counts.values()),
                source_checked_documents=counts["source_checked"],
                version=digest.hexdigest()[:16],
            )
            conn.execute(
                "UPDATE metadata SET value=? WHERE key='manifest'",
                (json.dumps(manifest, ensure_ascii=False),),
            )
            conn.commit()
            assert (
                conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                == conn.execute("SELECT count(*) FROM document_search").fetchone()[0]
            )
        finally:
            conn.close()
        staging.replace(destination)
        report = {
            "added": added,
            "documents": manifest["documents"],
            "source_checked_documents": manifest["source_checked_documents"],
            "version": manifest["version"],
            "source_files": ["curated_support.jsonl", "quality_support.jsonl"],
            "source_sha256": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in ["curated_support.jsonl", "quality_support.jsonl"]
                if (root / name).exists()
            },
        }
        (self.settings.reports_dir / "source-support.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    SourceImporter(Settings()).run()
