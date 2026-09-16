"""WHO fact-sheet collector: build a curated, source-traceable extension corpus.

Fetches the WHO Chinese fact-sheet index, downloads each page, extracts the
structured sections (overview / symptoms / causes / prevention / diagnosis /
complications / treatment), and emits Document records compatible with the
existing curated.jsonl schema (rag.entity.Evidence.Document), all marked
review_status="source_checked" because they carry a real source URL and are
published by an authoritative public-health source.

This script is READ-ONLY with respect to knowledge.sqlite: it writes only
jsonl fragments under data/curated_ext/. Publishing into the corpus is a
separate, explicit step.

Usage:
    python -m create_data.WHOCollector --limit 3            # dry run, few pages
    python -m create_data.WHOCollector --all               # full Chinese index
    python -m create_data.WHOCollector --all --out data/curated_ext.jsonl
"""

import argparse
import html as html_module
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "curated_ext.jsonl"

try:  # reuse the project's chunking so the fragments match the corpus protocol
    from create_data.BuildMedicalCorpus import chunks
except Exception:  # noqa: BLE001 - standalone fallback

    def chunks(text: str, limit=450, overlap=50):
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


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}

# Language profiles: index URL, detail URL prefix, index slug regex flag, facet rules.
ZH = {
    "index_url": "https://www.who.int/zh/news-room/fact-sheets",
    "detail_prefix": "https://www.who.int/zh/news-room/fact-sheets/detail/",
    "lang_seg": "/zh/",
}
EN = {
    "index_url": "https://www.who.int/news-room/fact-sheets",
    "detail_prefix": "https://www.who.int/news-room/fact-sheets/detail/",
    "lang_seg": "/",
}

FACET_RULES_ZH = [
    ("症状", "symptom"),
    ("体征", "symptom"),
    ("主要事实", "overview"),
    ("概述", "overview"),
    ("概况", "overview"),
    ("原因", "cause"),
    ("病因", "cause"),
    ("诱因", "cause"),
    ("危险因素", "cause"),
    ("风险因素", "cause"),
    ("传播", "cause"),
    ("如何传播", "cause"),
    ("预防", "prevention"),
    ("诊断", "test"),
    ("检查", "test"),
    ("如何诊断", "test"),
    ("并发症", "complication"),
    ("治疗", "treatment"),
    ("治疗方式", "treatment"),
    ("应对", "treatment"),
    ("类别", "overview"),
    ("定义", "overview"),
    ("常见问题", "overview"),
    ("关键", "overview"),
]
FACET_RULES_EN = [
    ("Symptoms", "symptom"),
    ("Signs", "symptom"),
    ("Key facts", "overview"),
    ("Overview", "overview"),
    ("What is", "overview"),
    ("About", "overview"),
    ("Causes", "cause"),
    ("Cause", "cause"),
    ("Risk factors", "cause"),
    ("Who is at risk", "cause"),
    ("Transmission", "cause"),
    ("How it spreads", "cause"),
    ("Prevention", "prevention"),
    ("Preventing", "prevention"),
    ("Diagnosis", "test"),
    ("Diagnosed", "test"),
    ("Tests", "test"),
    ("Checking", "test"),
    ("Complications", "complication"),
    ("Complication", "complication"),
    ("Treatment", "treatment"),
    ("Treating", "treatment"),
    ("Management", "treatment"),
    ("Response", "treatment"),
    ("Types", "overview"),
    ("Definition", "overview"),
]

CFG = ZH
CFG_FACETS = FACET_RULES_ZH


def fetch(url: str, retries: int = 3, timeout: int = 20) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001 - network retry
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def strip_tags(raw: str) -> str:
    return html_module.unescape(re.sub(r"<[^>]+>", " ", raw))


def clean_text(raw: str) -> str:
    return re.sub(r"\s+", " ", strip_tags(raw)).strip()


def extract_meta(txt: str) -> dict:
    meta = {}
    for name, pattern in (
        ("published_at", r'property="article:published_time"\s+content="([^"]+)"'),
        ("modified", r'property="article:modified_time"\s+content="([^"]+)"'),
        ("description", r'name="description"\s+content="([^"]+)"'),
    ):
        m = re.search(pattern, txt)
        if m:
            meta[name] = m.group(1)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", txt, re.S)
    if title:
        meta["title"] = clean_sections(title.group(1))
    return meta


def clean_sections(raw: str) -> str:
    return clean_text(raw)


@dataclass
class Child:
    text: str
    children: list = field(default_factory=list)


def extract_sections(txt: str) -> list:
    """Extract a flat list of (section_title, list_of_paragraph_texts)."""
    article = re.search(r"<article[^>]*>(.*?)</article>", txt, re.S)
    seg = article.group(1) if article else txt
    blocks = re.findall(r"<(h2|h3|p|li)[^>]*>(.*?)</\1>", seg, re.S)
    sections, current_title, current_body = [], "", []
    for tag, inner in blocks:
        text = clean_sections(inner)
        if not text:
            continue
        if tag in ("h2", "h3"):
            if current_title and current_body:
                sections.append((current_title, current_body))
            current_title, current_body = text, []
        else:
            current_body.append(text)
    if current_title and current_body:
        sections.append((current_title, current_body))
    return sections


def facet_for(title: str) -> str:
    for key, facet in CFG_FACETS:
        if key.lower() in title.lower():
            return facet
    return "overview"


def build_documents(slug: str, meta: dict, sections: list) -> list[dict]:
    """Turn one page into a list of curated.jsonl-compatible documents."""
    entity = meta.get("entity", meta.get("title", ""))
    published_at = (meta.get("published_at") or meta.get("modified") or "").split("T")[0] or None
    prefix = "who-en" if CFG == EN else "who"
    if not sections and len(meta.get("description", "")) > 30:
        sections = [("Overview" if CFG == EN else "概述", [meta["description"]])]
    docs = []
    for idx, (title, texts) in enumerate(sections):
        text = " ".join(t for t in texts if t) if isinstance(texts, list) else texts
        if len(text) < 30:
            continue
        facet = facet_for(title)
        for chunk_idx, chunk in enumerate(chunks(text)):
            docs.append(
                {
                    "id": f"{prefix}:{slug}:{facet}:{idx}:{chunk_idx}",
                    "source_id": f"who:{slug}",
                    "title": f"{entity} · {title}",
                    "text": chunk,
                    "entity": entity,
                    "facet": facet,
                    "source_title": f"WHO 事实清单 · {entity}",
                    "source_url": url_for(slug),
                    "source_type": "public_health",
                    "review_status": "source_checked",
                    "published_at": published_at,
                    "date_provenance": "publication_extracted"
                    if published_at
                    else "publication_not_extracted",
                    "language": "en" if CFG == EN else "zh",
                    "checked_at": date.today().isoformat(),
                    "version": "who-2026-09-07",
                    "aliases": [],
                }
            )
    return docs


def url_for(slug: str) -> str:
    return CFG["detail_prefix"].rstrip("/") + "/" + slug


def index_slugs() -> list[str]:
    txt = fetch(CFG["index_url"])
    seg = CFG["lang_seg"]
    pattern = rf'href="[^"]*{re.escape(seg)}news-room/fact-sheets/detail/([^"?#]+)"'
    slugs = []
    for match in re.finditer(pattern, txt):
        slug = match.group(1)
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="WHO index language")
    parser.add_argument("--all", action="store_true", help="process the whole index")
    parser.add_argument("--limit", type=int, default=3, help="max pages to process")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output jsonl path")
    args = parser.parse_args()

    global CFG, CFG_FACETS
    if args.lang == "en":
        CFG, CFG_FACETS = EN, FACET_RULES_EN
    else:
        CFG, CFG_FACETS = ZH, FACET_RULES_ZH

    slugs = index_slugs()
    if not args.all:
        slugs = slugs[: args.limit]
    print(f"[{args.lang}] index pages found: {len(slugs)}; processing {len(slugs)}", flush=True)

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_docs, failures = 0, []
    with out_path.open("w", encoding="utf-8") as out:
        for i, slug in enumerate(slugs, 1):
            if i > (args.limit if not args.all else len(slugs)):
                break
            try:
                txt = fetch(CFG["detail_prefix"] + slug)
                meta = extract_meta(txt)
                if "title" not in meta:
                    meta["title"] = slug
                meta["entity"] = meta["title"]
                sections = extract_sections(txt)
                docs = build_documents(slug, meta, sections)
                for doc in docs:
                    out.write(json.dumps(doc, ensure_ascii=False) + "\n")
                total_docs += len(docs)
                print(f"  [{i}/{len(slugs)}] {meta.get('entity', slug)!r} -> {len(docs)} docs", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append((slug, type(exc).__name__))
                print(f"  [{i}/{len(slugs)}] FAIL {slug}: {type(exc).__name__}", flush=True)
            time.sleep(0.3)
    print(f"done: {total_docs} docs written to {out_path}; failures={len(failures)}", flush=True)
    if failures:
        for slug, kind in failures[:20]:
            print(f"  failed: {slug} ({kind})", flush=True)


if __name__ == "__main__":
    main()
