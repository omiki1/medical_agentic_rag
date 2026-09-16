import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from common.ApplicationContext import ApplicationContext
from fastapi import HTTPException

from tests.test_contracts import Fixtures


class StreamLifecycleContracts(Fixtures):
    def setUp(self):
        self.context = ApplicationContext(self.settings, self.corpus, self.retriever)
        _, session = self.context.auth_dao.issue_session()
        self.owner = session["id"]
        self.dao = self.context.chat_dao
        self.cid = self.dao.create_conversation(self.owner)["id"]

    def tearDown(self):
        self.context.close()

    def request(self):
        return SimpleNamespace(
            conversation_id=self.cid,
            request_id=str(uuid.uuid4()),
            question="高血压有哪些症状",
            mode="exploratory",
        )

    def test_cancellation_releases_run_and_allows_next_request(self):
        async def hanging(*args, **kwargs):
            await asyncio.Event().wait()
            yield {}

        async def scenario():
            service = self.context.chat_service
            service.agent = SimpleNamespace(stream=hanging)
            stream = await service.chat(self.request(), self.owner)
            start = json.loads((await anext(stream))[6:])
            await stream.aclose()
            self.assertEqual(self.dao.run(self.owner, start["run_id"])["status"], "cancelled")
            service.agent = self.context.agent
            next_stream = await service.chat(self.request(), self.owner)
            events = [json.loads(event[6:]) async for event in next_stream if event.startswith("data: ")]
            self.assertEqual(events[-1]["type"], "done")
            self.assertEqual(self.dao.run(self.owner, events[-1]["run_id"])["status"], "completed")
            self.assertFalse(service.capacity.locked())

        asyncio.run(scenario())

    def test_timeout_is_durable_and_does_not_save_unverified_answer(self):
        async def hanging(*args, **kwargs):
            await asyncio.Event().wait()
            yield {}

        async def scenario():
            service = self.context.chat_service
            service.settings = self.settings.model_copy(update={"request_timeout": 0.03})
            service.agent = SimpleNamespace(stream=hanging)
            stream = await service.chat(self.request(), self.owner)
            events = [json.loads(event[6:]) async for event in stream if event.startswith("data: ")]
            self.assertEqual(events[-1]["code"], "timeout")
            stored = self.dao.run(self.owner, events[0]["run_id"])
            self.assertEqual(stored["status"], "timeout")
            self.assertIsNone(stored["result"])
            self.assertFalse(service.capacity.locked())

        asyncio.run(scenario())

    def test_waiting_for_capacity_counts_toward_request_timeout(self):
        async def scenario():
            service = self.context.chat_service
            service.settings = self.settings.model_copy(update={"request_timeout": 0.03})
            stream = await service.chat(self.request(), self.owner)
            limit = service.settings.max_concurrent_chats
            for _ in range(limit):
                await service.capacity.acquire()
            try:
                events = [json.loads(e[6:]) async for e in stream if e.startswith("data: ")]
                self.assertEqual(events[-1]["code"], "timeout")
                self.assertFalse(any(e["type"] == "result" for e in events))
            finally:
                for _ in range(limit):
                    service.capacity.release()
        asyncio.run(scenario())

    def test_capacity_and_rate_limit_fail_before_creating_runs(self):
        async def scenario():
            service = self.context.chat_service
            limit = service.settings.max_concurrent_chats
            for _ in range(limit):
                await service.capacity.acquire()
            try:
                with self.assertRaises(HTTPException) as error:
                    await service.chat(self.request(), self.owner)
                self.assertEqual(error.exception.status_code, 503)
                self.assertEqual(self.dao.conversation(self.owner, self.cid)["runs"], [])
            finally:
                for _ in range(limit):
                    service.capacity.release()
            service.settings = self.settings.model_copy(update={"requests_per_minute": 1})
            with self.assertRaises(HTTPException) as error:
                service.check_rate(self.owner)
            self.assertEqual(error.exception.status_code, 429)
        asyncio.run(scenario())

    def test_ten_distinct_users_can_run_simultaneously_and_eleventh_is_rejected(self):
        async def hanging(*args, **kwargs):
            await asyncio.Event().wait()
            yield {}

        async def scenario():
            service = self.context.chat_service
            service.agent = SimpleNamespace(stream=hanging)
            self.assertEqual(service.settings.max_concurrent_chats, 10)
            streams = []
            for _ in range(10):
                _, session = self.context.auth_dao.issue_session()
                owner = session["id"]
                cid = self.dao.create_conversation(owner)["id"]
                body = SimpleNamespace(
                    conversation_id=cid,
                    request_id=str(uuid.uuid4()),
                    question="并发容量测试",
                    mode="authoritative",
                )
                streams.append(await service.chat(body, owner))
            starts = await asyncio.gather(*(anext(stream) for stream in streams))
            self.assertTrue(all(json.loads(frame[6:])["type"] == "start" for frame in starts))
            self.assertTrue(service.capacity.locked())

            _, extra_session = self.context.auth_dao.issue_session()
            extra_owner = extra_session["id"]
            extra_cid = self.dao.create_conversation(extra_owner)["id"]
            extra = SimpleNamespace(
                conversation_id=extra_cid,
                request_id=str(uuid.uuid4()),
                question="第十一个请求",
                mode="authoritative",
            )
            with self.assertRaises(HTTPException) as error:
                await service.chat(extra, extra_owner)
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(self.dao.conversation(extra_owner, extra_cid)["runs"], [])
            await asyncio.gather(*(stream.aclose() for stream in streams))
            self.assertFalse(service.capacity.locked())

        asyncio.run(scenario())

    def test_provider_exception_is_redacted_and_releases_capacity(self):
        async def failing(*args, **kwargs):
            raise RuntimeError("private-provider-token-123")
            yield {}
        async def scenario():
            service = self.context.chat_service
            service.agent = SimpleNamespace(stream=failing)
            stream = await service.chat(self.request(), self.owner)
            events = [json.loads(e[6:]) async for e in stream if e.startswith("data: ")]
            self.assertEqual(events[-1]["code"], "unavailable")
            self.assertNotIn("private-provider-token", str(events))
            run = self.dao.run(self.owner, events[0]["run_id"])
            self.assertEqual(run["status"], "failed")
            self.assertIsNone(run["result"])
            self.assertFalse(service.capacity.locked())
        asyncio.run(scenario())

    def test_cache_failure_does_not_discard_a_validated_answer(self):
        async def scenario():
            service = self.context.chat_service
            service.memory = SimpleNamespace(resolve=self.context.memory_service.resolve,
                                             refresh=Mock(side_effect=ConnectionError("cache down")))
            service.translator = SimpleNamespace(lookup=Mock(side_effect=OSError("cache down")))
            stream = await service.chat(self.request(), self.owner)
            events = [json.loads(e[6:]) async for e in stream if e.startswith("data: ")]
            self.assertEqual(events[-1]["type"], "done")
            self.assertEqual(self.dao.run(self.owner, events[-1]["run_id"])["status"], "completed")
        asyncio.run(scenario())

    def test_source_display_only_uses_cached_translation(self):
        translator = SimpleNamespace(lookup=Mock(return_value={"text_zh": "来源译文"}),
                                     translate_enough=Mock(side_effect=AssertionError("unexpected model call")))
        self.context.chat_service.translator = translator
        result = {"evidence": [{"document": {"id": "public", "text": "Public information."}}]}
        asyncio.run(self.context.chat_service.enrich_result(result))
        self.assertEqual(result["evidence"][0]["document"]["text_zh"], "来源译文")
        translator.translate_enough.assert_not_called()
