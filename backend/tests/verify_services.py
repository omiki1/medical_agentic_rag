"""Explicit local integration check. Creates and cleans only test-owned records."""

import asyncio
import json
import time
import uuid

from ai.LLMService import LLMService
from ai.Neo4jService import Neo4jService
from auth.dao.AuthDao import AuthDao
from chat.dao.ChatDao import ChatDao
from common.Database import Database
from common.Schema import Schema
from common.Settings import Settings
from memory.layers.RedisMemory import RedisMemory


async def main():
    settings = Settings()
    report = {}
    for dialect in ["mysql", "postgres"]:
        local = settings.model_copy(update={"database_backend": dialect})
        database = Database(local)
        Schema.initialize(database)
        auth = AuthDao(database, 1)
        token, session = auth.issue_session()
        owner = session["id"]
        try:
            assert auth.find_session(token)["id"] == owner
            dao = ChatDao(database)
            cid = dao.create_conversation(owner, "integration-test")["id"]
            rid = dao.start_run(owner, cid, str(uuid.uuid4()), "integration-test")
            dao.finish_run(owner, rid, {"status": "answered", "answer": "测试", "evidence": []})
            assert dao.run(owner, rid)["status"] == "completed"
            assert dao.conversation("different-owner", cid) is None
            report[dialect] = "schema, transaction, owner isolation and persistence passed"
        finally:
            with database.connect() as conn:
                conn.execute("DELETE FROM sessions WHERE id=?", (owner,))
    graph = Neo4jService(settings)
    try:
        rows = graph.query(["糖尿病"], ["DISEASE_DRUG"], 3)
        assert graph.status == "connected" and rows
        report["neo4j"] = {"status": graph.status, "sample_edges": len(rows)}
    finally:
        graph.close()
    redis = RedisMemory(settings)
    report["redis"] = redis.status
    redis.close()
    for role in ["answer", "agent"]:
        started = time.perf_counter()
        budget = {"calls": 0, "conversation_id": "integration-" + uuid.uuid4().hex}
        gateway = LLMService(settings, role=role)
        try:
            value = await gateway.json(
                '返回 JSON {"ok":true}，用于服务连通性检查。', {"check": "connection"}, budget
            )
            report[role + "_llm"] = {
                "model": gateway.model,
                "ok": value.get("ok") is True,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "calls": budget["calls"],
            }
        except Exception as error:
            report[role + "_llm"] = {"model": gateway.model, "ok": False, "error_type": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    (settings.reports_dir / "services.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
