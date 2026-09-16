"""Append the user's WHO exports while preserving every existing document and graph edge."""

import hashlib
import json
import sqlite3
from collections import Counter
from urllib.parse import urlparse

from common.Settings import Settings
from rag.BM25Retriever import tokenize
from rag.entity.Evidence import Document


class WHOMerger:
    def __init__(self, settings):
        self.settings = settings

    def run(self):
        root = self.settings.data_dir
        destination = root / "knowledge.sqlite"
        staging = root / "knowledge.who.sqlite"
        backup = root / "knowledge.before-who.sqlite"
        source = sqlite3.connect(destination)
        before = dict(source.execute("SELECT review_status,count(*) FROM documents GROUP BY review_status"))
        edges_before = source.execute("SELECT count(*) FROM edges").fetchone()[0]
        if not backup.exists():
            with sqlite3.connect(backup) as archive:
                source.backup(archive)
        conn = sqlite3.connect(staging)
        source.backup(conn)
        source.close()
        counts = Counter()
        files = [root / "curated_ext.jsonl", root / "curated_ext_en.jsonl"]
        canonical = {}
        english_names = {}
        for (body,) in conn.execute("SELECT body FROM documents WHERE review_status='source_checked'"):
            doc = json.loads(body)
            canonical[urlparse(doc["source_url"]).path.rsplit("/", 1)[-1]] = doc["entity"]
        for path in files:
            with path.open(encoding="utf-8-sig") as stream:
                for line in stream:
                    row = json.loads(line)
                    slug = urlparse(row["source_url"]).path.rsplit("/", 1)[-1]
                    if path.name == "curated_ext.jsonl":
                        canonical.setdefault(slug, row["entity"])
                    else:
                        english_names[slug] = row["entity"]
        try:
            for path in files:
                with path.open(encoding="utf-8-sig") as stream:
                    for line_no, line in enumerate(stream, 1):
                        raw = json.loads(line)
                        counts["input_rows"] += 1
                        parsed = urlparse(raw.get("source_url", ""))
                        if (
                            parsed.scheme != "https"
                            or parsed.hostname != "www.who.int"
                            or "/fact-sheets/detail/" not in parsed.path
                        ):
                            raise ValueError(f"Unexpected WHO provenance at {path.name}:{line_no}")
                        slug = parsed.path.rsplit("/", 1)[-1]
                        aliases = {raw["entity"], *raw.get("aliases", [])}
                        if slug in english_names:
                            aliases.add(english_names[slug])
                        raw["entity"] = canonical.get(slug, raw["entity"])
                        raw["aliases"] = sorted(aliases - {raw["entity"]})
                        raw["source_id"] = "who:" + slug
                        raw["language"] = "zh" if "/zh/" in parsed.path else "en"
                        raw["source_file"], raw["source_line"] = path.name, line_no
                        # Collector used today's date as fallback. Do not pretend it is publication evidence.
                        if raw.get("published_at") == raw.get("checked_at"):
                            raw["published_at"] = None
                            raw["date_provenance"] = "publication_unknown_collector_fallback_removed"
                            counts["publication_fallback_removed"] += 1
                        doc = Document.model_validate(raw)
                        previous = conn.execute(
                            "SELECT source_id FROM documents WHERE id=?", (doc.id,)
                        ).fetchone()
                        if previous:
                            counts["existing_skipped"] += 1
                            continue
                        conn.execute(
                            "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                            (
                                doc.id,
                                doc.source_id,
                                doc.entity,
                                doc.facet,
                                doc.review_status,
                                doc.model_dump_json(),
                            ),
                        )
                        counts["added_" + doc.language] += 1
            # A disk index makes all historical texts searchable without huge in-memory postings.
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(tokens)")
            conn.execute("DELETE FROM document_search")
            for rowid, body in conn.execute("SELECT rowid,body FROM documents"):
                doc = Document.model_validate_json(body)
                conn.execute(
                    "INSERT INTO document_search(rowid,tokens) VALUES (?,?)",
                    (rowid, " ".join(tokenize(doc.title + " " + doc.text))),
                )
            original = json.loads(
                conn.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0]
            )
            digest = hashlib.sha256()
            for (body,) in conn.execute("SELECT body FROM documents ORDER BY id"):
                digest.update(body.encode())
            after = dict(conn.execute("SELECT review_status,count(*) FROM documents GROUP BY review_status"))
            edges_after = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
            assert after["unreviewed"] == before["unreviewed"] and edges_after == edges_before
            original.update(
                documents=sum(after.values()),
                source_checked_documents=after["source_checked"],
                version=digest.hexdigest()[:16],
                who_extension_rows=original.get("who_extension_rows", 0)
                + counts["added_zh"]
                + counts["added_en"],
                lexical_index="sqlite_fts5_bigrams",
            )
            conn.execute(
                "UPDATE metadata SET value=? WHERE key='manifest'",
                (json.dumps(original, ensure_ascii=False),),
            )
            conn.commit()
            report = {
                **counts,
                "before": before,
                "after": after,
                "edges_before": edges_before,
                "edges_after": edges_after,
                "legacy_unchanged": True,
                "neo4j_writes": 0,
                "version": original["version"],
            }
        finally:
            conn.close()
        staging.replace(destination)
        (self.settings.reports_dir / "who-merge.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report


if __name__ == "__main__":
    WHOMerger(Settings()).run()
