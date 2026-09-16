"""Retrieval visualizer: a zero-dependency read-only web server.

Serves one self-contained HTML page plus a JSON endpoint built from:
  - reports/retrieval-details.json  (per-case gold/retrieved + metrics)
  - reports/evaluation.json         (ablation summary)
  - data/knowledge.sqlite           (doc id -> human-readable title/entity/facet)

Only the document ids actually referenced by the reports are looked up, so
startup stays fast despite the large corpus.
"""

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
REPORTS = PROJECT / "reports"
DETAILS_PATH = REPORTS / "retrieval-details.json"
EVAL_PATH = REPORTS / "evaluation.json"
KNOWLEDGE_PATH = PROJECT / "data" / "knowledge.sqlite"

HOST = "127.0.0.1"
PORT = 8020


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload():
    details = _read_json(DETAILS_PATH)
    evaluation = _read_json(EVAL_PATH)

    ids: set[str] = set()
    for item in details:
        ids.update(item.get("gold", []))
        ids.update(item.get("retrieved", []))

    doc_map = {}
    if KNOWLEDGE_PATH.exists():
        conn = sqlite3.connect(KNOWLEDGE_PATH.as_uri() + "?mode=ro", uri=True)
        try:
            for doc_id in ids:
                row = conn.execute("SELECT body FROM documents WHERE id=?", (doc_id,)).fetchone()
                if not row:
                    continue
                body = json.loads(row[0])
                doc_map[doc_id] = {
                    "id": doc_id,
                    "title": body.get("title") or doc_id,
                    "entity": body.get("entity", ""),
                    "facet": body.get("facet", ""),
                    "source_title": body.get("source_title", ""),
                    "source_url": body.get("source_url", ""),
                    "review_status": body.get("review_status", ""),
                }
        finally:
            conn.close()

    return {"details": details, "evaluation": evaluation, "doc_map": doc_map}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/retrieval":
            payload = build_payload()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args):
        pass


def main():
    build_payload()  # validate data sources before serving
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Retrieval visualizer listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
