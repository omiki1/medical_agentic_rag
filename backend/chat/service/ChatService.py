import asyncio
import contextlib
import json
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException

logger = logging.getLogger("mediatlas")


class ChatService:
    """Request ownership, memory resolution, bounded streaming and durable completion."""

    def __init__(self, dao, agent, memory, settings, translator=None):
        self.dao, self.agent, self.memory, self.settings = dao, agent, memory, settings
        self.translator = translator
        self.capacity = asyncio.Semaphore(settings.max_concurrent_chats)
        self.limits = defaultdict(deque)

    async def chat(self, body, owner, agent=None):
        cid, request_id = str(body.conversation_id), str(body.request_id)
        conversation = self.dao.conversation(owner, cid)
        if not conversation:
            raise HTTPException(404, "未找到对话")
        previous = self.dao.find_request(owner, request_id)
        if previous:
            if (
                previous["conversation_id"] != cid
                or previous["question"] != body.question
                or previous.get("mode", "authoritative") != body.mode
            ):
                raise HTTPException(409, "请求标识已用于不同问题")
            if previous["status"] == "completed":

                async def replay():
                    yield self.encode({"type": "result", "data": previous["result"]})
                    yield self.encode({"type": "done", "run_id": previous["id"], "replayed": True})

                return replay()
            raise HTTPException(409, "请求已提交，请查看历史或重试")
        self.check_rate(owner)
        if body.mode == "exploratory":
            reason = self.exploration_unavailable(agent or self.agent)
            if reason:
                raise HTTPException(503, reason)
        if self.capacity.locked():
            raise HTTPException(503, "当前任务较多，请稍后再试", headers={"Retry-After": "3"})
        memory = await asyncio.to_thread(self.memory.resolve, owner, conversation, body.question)
        try:
            rid = self.dao.start_run(owner, cid, request_id, body.question, body.mode)
        except (ValueError, LookupError) as error:
            raise HTTPException(409, str(error)) from error
        return self.stream(owner, cid, rid, body.question, memory, body.mode, agent=agent)

    @staticmethod
    def exploration_unavailable(agent):
        """探索模式此刻无法安全处理请求时返回原因字符串；可用则返回 None。

        判定逻辑放在检索器里（HybridRetriever.exploration_blocked_reason），
        因为它才知道"会不会真的触发一次 60-90 分钟的编码"。
        这里只做防御性调用：拿不到检索器时绝不阻断请求。
        """
        retriever = getattr(getattr(agent, "rag", None), "retriever", None)
        reason = getattr(retriever, "exploration_blocked_reason", None)
        if not callable(reason):
            return None
        try:
            return reason()
        except Exception:
            return None

    def check_rate(self, owner):
        now = time.monotonic()
        for key in list(self.limits):
            if not self.limits[key] or self.limits[key][-1] < now - 60:
                del self.limits[key]
        window = self.limits[owner]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= self.settings.requests_per_minute:
            raise HTTPException(429, "请求过于频繁，请稍后重试", headers={"Retry-After": "60"})
        window.append(now)

    @staticmethod
    def encode(event):
        return "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"

    async def enrich_result(self, data: dict):
        """Attach cached translations without adding model calls to answer delivery.

        A source-detail request can translate a cache miss separately. Presentation
        work must not consume a second model budget or time out a validated answer.
        """
        if not self.translator:
            return
        evidence = data.get("evidence") or []
        if not evidence:
            return
        for ev in evidence:
            doc = ev.get("document") if isinstance(ev, dict) else None
            if not isinstance(doc, dict):
                continue
            try:
                row = self.translator.lookup(doc.get("text") or "")
            except Exception:
                continue
            if not row:
                continue
            if row.get("title_zh"):
                doc["title_zh"] = row["title_zh"]
            if row.get("text_zh"):
                doc["text_zh"] = row["text_zh"]

    async def stream(self, owner, cid, rid, question, memory, mode="authoritative", agent=None):
        queue = asyncio.Queue(maxsize=30)

        async def produce():
            try:
                async with asyncio.timeout(self.settings.request_timeout), self.capacity:
                    await queue.put({"type": "start", "run_id": rid, "conversation_id": cid})
                    async for event in (agent or self.agent).stream(
                        question, rid, memory=memory, conversation_id=cid, mode=mode
                    ):
                        if event["type"] == "result":
                            await self.enrich_result(event["data"])
                            self.dao.finish_run(owner, rid, event["data"])
                            try:
                                await asyncio.wait_for(
                                    asyncio.to_thread(self.memory.refresh, owner, cid), timeout=2
                                )
                            except Exception as error:
                                logger.warning("memory_refresh_failed run_id=%s error_type=%s", rid, type(error).__name__)
                        await queue.put(event)
                    await queue.put({"type": "done", "run_id": rid})
            except asyncio.CancelledError:
                self.dao.mark_run(owner, rid, "cancelled")
                raise
            except TimeoutError:
                self.dao.mark_run(owner, rid, "timeout")
                await queue.put(
                    {
                        "type": "error",
                        "code": "timeout",
                        "message": "请求超时。未经验证的回答未被保存，请缩小问题范围后重试。",
                    }
                )
            except Exception as error:
                self.dao.mark_run(owner, rid, "failed")
                logger.error("run_failed run_id=%s error_type=%s", rid, type(error).__name__)
                await queue.put(
                    {"type": "error", "code": "unavailable", "message": "处理暂未完成，请稍后重试。"}
                )
            finally:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    if producer.done() and queue.empty():
                        break
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    break
                yield self.encode(event)
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
            self.dao.mark_run(owner, rid, "cancelled")
