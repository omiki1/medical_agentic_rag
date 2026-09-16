"""Streaming ingestion. Documents and graph edges share the same immutable source ID.

Imported material is NEVER promoted to reviewed evidence by an import command.
"""

import hashlib
import html
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from rag.entity.Evidence import Document

FACETS = {
    "desc": ("overview", "概述"),
    "symptom": ("symptom", "症状"),
    "cause": ("cause", "病因"),
    "prevent": ("prevention", "预防"),
    "cure_department": ("department", "就诊科室"),
    "cure_way": ("treatment", "治疗方式"),
    "check": ("test", "检查"),
    "recommand_drug": ("medication", "相关药物"),
    "acompany": ("complication", "并发症"),
    "do_eat": ("diet", "饮食"),
    "not_eat": ("diet", "不宜饮食"),
}
RELATIONS = {
    "symptom": "DISEASE_SYMPTOM",
    "cure_department": "DISEASE_DEPARTMENT",
    "cure_way": "DISEASE_CUREWAY",
    "check": "DISEASE_CHECK",
    "recommand_drug": "DISEASE_DRUG",
    "acompany": "DISEASE_ACOMPANY",
    "do_eat": "DISEASE_DO_EAT",
    "not_eat": "DISEASE_NOT_EAT",
}


def clean(value) -> str:
    value = "；".join(str(x) for x in value if x) if isinstance(value, list) else str(value or "")
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def chunks(text: str, limit=450, overlap=50):
    """Actually yield separate chunks, splitting near sentence boundaries."""
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            stop = max(text.rfind(p, start + limit // 2, end) for p in "。！？；")
            if stop >= 0:
                end = stop + 1
        yield text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def read_rows(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        first = stream.read(1)
        stream.seek(0)
        if first == "[":
            # Small structured exports; use JSONL for million-row corpora.
            if path.stat().st_size > 128 * 1024 * 1024:
                raise ValueError("Large imports must use streaming JSONL")
            yield from json.load(stream)
        else:
            for number, line in enumerate(stream, 1):
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"Invalid JSON at line {number}") from error


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, entity TEXT NOT NULL,
 facet TEXT NOT NULL, review_status TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS doc_entity ON documents(entity);
CREATE INDEX IF NOT EXISTS doc_source ON documents(source_id);
CREATE TABLE IF NOT EXISTS edges (
 subject TEXT, relation TEXT, object TEXT, doc_id TEXT REFERENCES documents(id),
 PRIMARY KEY(subject,relation,object,doc_id));
CREATE INDEX IF NOT EXISTS edge_subject ON edges(subject);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def insert_doc(conn, doc: Document):
    conn.execute(
        "INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?)",
        (doc.id, doc.source_id, doc.entity, doc.facet, doc.review_status, doc.model_dump_json()),
    )


def build_corpus(
    destination: Path,
    seed: Path,
    medical: Path | None = None,
    qa: Path | None = None,
    qa_limit: int | None = None,
):
    """Build a new version transactionally, then atomically publish the SQLite file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".building.sqlite")
    if temp.exists():
        temp.unlink()
    report = {"medical_rows": 0, "diseases": 0, "duplicates": 0, "invalid": 0, "qa_rows": 0}
    conn = sqlite3.connect(temp)
    try:
        conn.executescript(SCHEMA)
        for row in read_rows(seed):
            raw = dict(row)
            edges = raw.pop("edges", [])
            doc = Document.model_validate(raw)
            insert_doc(conn, doc)
            for relation, target in edges:
                if relation not in RELATIONS.values():
                    raise ValueError(f"Unknown seed relation: {relation}")
                conn.execute(
                    "INSERT OR IGNORE INTO edges VALUES (?,?,?,?)", (doc.entity, relation, target, doc.id)
                )
        seen = set()
        if medical:
            report["medical_sha256"] = hashlib.sha256(medical.read_bytes()).hexdigest()
            for row in read_rows(medical):
                report["medical_rows"] += 1
                name, description = clean(row.get("name")), clean(row.get("desc"))
                if not name or not description:
                    report["invalid"] += 1
                    continue
                if name in seen:
                    report["duplicates"] += 1
                    continue
                seen.add(name)
                source_id = "legacy:" + stable_id(name)
                for field, (facet, label) in FACETS.items():
                    text = clean(row.get(field))
                    if not text:
                        continue
                    for index, chunk in enumerate(chunks(text)):
                        doc = Document(
                            id=stable_id(source_id, field, str(index), chunk),
                            source_id=source_id,
                            title=f"{name} · {label}",
                            text=f"{name}：{chunk}",
                            entity=name,
                            facet=facet,
                            source_title="原始 medical.json（出处与医学内容待复核）",
                        )
                        insert_doc(conn, doc)
                        if field in RELATIONS:
                            values = row[field] if isinstance(row[field], list) else [row[field]]
                            for target in values:
                                target = clean(target)
                                if target:
                                    conn.execute(
                                        "INSERT OR IGNORE INTO edges VALUES (?,?,?,?)",
                                        (name, RELATIONS[field], target, doc.id),
                                    )
                if report["medical_rows"] % 500 == 0:
                    conn.commit()
        report["diseases"] = len(seen)
        if qa:
            for row in read_rows(qa):
                question = clean(row.get("prompt", row.get("question")))
                response = clean(row.get("response", row.get("answer")))
                if not question or not response:
                    report["invalid"] += 1
                    continue
                if qa_limit is not None and report["qa_rows"] >= qa_limit:
                    break
                source_id = "qa:" + stable_id(question, response)
                for index, chunk in enumerate(chunks(response)):
                    insert_doc(
                        conn,
                        Document(
                            id=stable_id(source_id, str(index)),
                            source_id=source_id,
                            title=question[:100],
                            text=f"问题：{question}\n回答：{chunk}",
                            source_type="qa",
                            source_title="导入 QA 语料（待医学复核）",
                        ),
                    )
                report["qa_rows"] += 1
                if report["qa_rows"] % 500 == 0:
                    conn.commit()
        report["documents"] = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        report["edges"] = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
        report["source_checked_documents"] = conn.execute(
            "SELECT count(*) FROM documents WHERE review_status='source_checked'"
        ).fetchone()[0]
        digest = hashlib.sha256()
        for (body,) in conn.execute("SELECT body FROM documents ORDER BY id"):
            digest.update(body.encode())
        report["version"] = digest.hexdigest()[:16]
        conn.execute("INSERT INTO metadata VALUES ('manifest',?)", (json.dumps(report, ensure_ascii=False),))
        conn.commit()
    finally:
        conn.close()
    temp.replace(destination)
    return report


class CorpusBuilder:
    """疾病/QA 流式导入、去重、同源图谱和版本发布。"""

    build = staticmethod(build_corpus)
    clean = staticmethod(clean)
    chunks = staticmethod(chunks)
