import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from create_data.BuildMedicalCorpus import build_corpus

from rag.entity.Evidence import Document


class MedicalCorpus:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "knowledge.sqlite"
        if not self.path.exists():
            build_corpus(self.path, data_dir / "curated.jsonl")
        with self.connect() as conn:
            self.drug_names = {
                row[0]
                for row in conn.execute("SELECT DISTINCT object FROM edges WHERE relation='DISEASE_DRUG'")
                if len(row[0]) >= 3
            }
            self.manifest = json.loads(
                conn.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0]
            )
            self.documents = {
                d.id: d
                for (body,) in conn.execute("SELECT body FROM documents")
                for d in [Document.model_validate_json(body)]
            }
        self.reviewed = [d for d in self.documents.values() if d.review_status == "source_checked"]
        self.entities = set(d.entity for d in self.documents.values() if d.entity)
        self.by_entity = defaultdict(list)
        self.aliases = {}
        for doc in self.documents.values():
            self.by_entity[doc.entity].append(doc.id)
            if doc.entity:
                self.aliases[doc.entity.lower()] = doc.entity
            for alias in doc.aliases:
                self.aliases[alias.lower()] = doc.entity
        # Source-checked normalization wins over homonyms in historical imports.
        for doc in self.reviewed:
            for alias in [doc.entity, *doc.aliases]:
                self.aliases[alias.lower()] = doc.entity

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def graph(self, entity, relations=None, limit=40):
        relations = relations or []
        sql = "SELECT subject,relation,object,doc_id FROM edges WHERE subject=?"
        values = [entity]
        if relations:
            sql += " AND relation IN (" + ",".join("?" for _ in relations) + ")"
            values.extend(relations)
        sql += " ORDER BY doc_id,relation,object LIMIT ?"
        values.append(min(limit, 100))
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, values)]
