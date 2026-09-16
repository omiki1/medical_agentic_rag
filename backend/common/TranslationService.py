"""English → Chinese translation for source display and answer excerpts.

Translation only affects presentation wording, never evidence identity or the
citation gates: grading always runs against the original source text. Results
are cached in an append-only JSONL under the data directory, keyed by the
SHA-256 of the original text, so repeated questions pay no extra API cost.
"""

import hashlib
import json
import re
import threading
from pathlib import Path

from ai.LLMService import LLMService

LATIN = re.compile(r"[A-Za-z]")
CJK = re.compile(r"[\u3400-\u9fff]")
# The English WHO collector wrote some Chinese labels in the wrong encoding.
MOJIBAKE = {"浜嬪疄娓呭崟": "事实清单", "浜嬪疄娓呭崟路": "事实清单", "路": "·"}


def is_english(text: str) -> bool:
    """Heuristic: the text is mostly Latin letters rather than CJK."""
    if not text or len(text.strip()) < 10:
        return False
    latin = len(LATIN.findall(text))
    cjk = len(CJK.findall(text))
    letters = latin + cjk
    if letters == 0 or latin < 10:
        return False
    return latin / letters > 0.6


def clean_title(title: str) -> str:
    """Repair the known mojibake in English WHO titles/source names."""
    if not title:
        return title
    cleaned = title
    for wrong, right in MOJIBAKE.items():
        cleaned = cleaned.replace(wrong, right)
    return cleaned


class TranslationService:
    INSTRUCTION = (
        "你是医学资料翻译。把英文内容翻译成通顺、准确、自然的简体中文；"
        "保留数字、单位、剂量与药物名等专有名词（首次出现时可附英文原名）。"
        "不要添加原文之外的说明、解释或免责声明。"
        '返回 {"title_zh": "中文标题", "text_zh": "中文正文"}。'
    )

    def __init__(self, settings):
        self.settings = settings
        self.cache_file: Path = settings.data_dir / "translations-cache.jsonl"
        self.cache: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.gateway = None
        if settings.provider == "compatible" and settings.llm_api_key:
            self.gateway = LLMService(
                settings.model_copy(update={"max_model_calls": 8}),
                role="answer",
            )
        self._load()

    @property
    def available(self) -> bool:
        return self.gateway is not None

    def _load(self):
        if not self.cache_file.exists():
            return
        try:
            with self.cache_file.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and "sha" in row and isinstance(row.get("text_zh"), str):
                        self.cache[row["sha"]] = row
        except OSError:
            self.cache = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def lookup(self, text: str):
        return self.cache.get(self._key(text))

    async def translate(self, text: str, title: str = "", budget=None) -> dict | None:
        """Translate one English text (title optional). Returns {title_zh, text_zh} or None."""
        if not self.available or not is_english(text):
            return None
        key = self._key(text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        budget = budget or {"calls": 0, "session_id": "translation"}
        try:
            data = await self.gateway.json(
                self.INSTRUCTION,
                {"title": clean_title(title) or None, "text": text},
                budget,
                max_calls=8,
            )
            translated = str(data.get("text_zh") or "").strip()
            if not translated or translated == text:
                return None
            row = {
                "sha": key,
                "title_zh": str(data.get("title_zh") or "").strip() or clean_title(title),
                "text_zh": translated,
            }
            with self.lock:
                self.cache[key] = row
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            return row
        except Exception:
            return None

    async def translate_enough(
        self, candidates: list[dict], budget=None, cap: int = 6
    ) -> dict[str, dict]:
        """Translate up to `cap` English docs from serialized document dicts.

        Returns {document_id: {title_zh, text_zh}}. Already-cached hits are free
        and do not count against the cap.
        """
        budget = budget or {"calls": 0, "session_id": "translation"}
        result: dict[str, dict] = {}
        for doc in candidates:
            text = doc.get("text") or ""
            if not is_english(text):
                continue
            if doc.get("text_zh"):
                result[doc["id"]] = {"title_zh": doc.get("title_zh"), "text_zh": doc["text_zh"]}
                continue
            if doc["id"] in result or budget["calls"] >= cap:
                continue
            translated = await self.translate(text, doc.get("title") or "", budget)
            if translated:
                result[doc["id"]] = translated
        return result