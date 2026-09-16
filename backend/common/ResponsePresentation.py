"""Public response allowlists; persistence retains diagnostics for administrators."""

import json
import re
from urllib.parse import urlparse


class ResponsePresentation:
    @staticmethod
    def source_title(doc):
        title = doc.get("source_title") or ""
        if re.search(r"\.(?:jsonl?|sqlite|csv|parquet)\b|[a-z]:[\\/]|file://", title, re.I):
            return "医学知识资料"
        return title or "医学知识资料"

    @classmethod
    def document(cls, doc):
        result = {
            k: doc[k]
            for k in ("id", "title", "title_zh", "text", "text_zh", "published_at", "review_status")
            if k in doc
        }
        result["source_title"] = cls.source_title(doc)
        url = doc.get("source_url") or ""
        parsed = urlparse(url)
        if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username:
            result["source_url"] = url
        return result

    @classmethod
    def result(cls, data):
        if not data:
            return data
        result = {
            k: data[k] for k in ("answer", "status", "mode", "duration_ms", "generation_mode") if k in data
        }
        result["evidence"] = [
            {"citation_id": ev.get("citation_id"), "document": cls.document(ev["document"])}
            for ev in data.get("evidence", [])
        ]
        return result

    @classmethod
    def run(cls, run):
        return {
            k: cls.result(v) if k == "result" else v
            for k, v in run.items()
            if k in {"id", "conversation_id", "question", "status", "created", "mode", "result"}
        }

    @classmethod
    def conversation(cls, data):
        return {
            k: [cls.run(r) for r in v] if k == "runs" else v
            for k, v in data.items()
            if k in {"id", "title", "created", "updated", "runs"}
        }

    @classmethod
    async def stream(cls, stream):
        # ChatService emits one complete JSON SSE frame per yield, including replay.
        try:
            async for frame in stream:
                if not frame.startswith("data: "):
                    yield frame
                    continue
                event = json.loads(frame[6:])
                if event.get("type") == "trace":
                    continue
                if event.get("type") == "result":
                    event["data"] = cls.result(event["data"])
                elif event.get("type") not in {"start", "done", "error"}:
                    continue
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            await stream.aclose()
