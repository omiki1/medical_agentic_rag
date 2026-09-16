"""Sequential synthetic dialogues through real ChatService + configured persistence.

Never reads an existing user's conversations. Each scenario gets a fresh guest
owner and conversation; only explicitly created test IDs are used. The report
keeps full outputs for human adjudication, not a model-generated quality score.
"""

import argparse
import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from agent.MedicalAgent import DISCLAIMER
from common.ApplicationContext import ApplicationContext
from common.Settings import ROOT, Settings


def fingerprint():
    digest = hashlib.sha256()
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {"tests", "evaluation", "__pycache__"} for part in path.relative_to(ROOT).parts):
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def run(llm=False, prepare=False, output=None):
    settings = Settings()
    if not llm or prepare:
        settings = settings.model_copy(update={"provider": "extractive"})
    case_path = Path(__file__).with_name("industrial_dialogues.json")
    scenarios = json.loads(case_path.read_text(encoding="utf-8"))
    start_hash = fingerprint()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "code_sha256_start": start_hash,
        "case_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
        "case_definitions": scenarios,
        "llm": llm and not prepare,
        "scope": "合成多轮工程验收；自动契约检查不等于医学正确性或实用性评分。",
        "turns": [],
    }
    name = output or ("industrial-preview" if prepare else "industrial-dialogues")
    report_path = settings.reports_dir / (name + ".json")
    progress = settings.reports_dir / (name + ".progress.jsonl")
    progress.write_text("", encoding="utf-8")
    context = ApplicationContext(settings)
    try:
        report["corpus_version"] = context.corpus.manifest["version"]
        report["runtime"] = {
            "database": settings.database_backend,
            "redis": context.memory_service.redis_status,
            "neo4j_driver": context.neo4j.driver is not None,
            "dense_reviewed_documents": len(context.retriever.dense.documents) if context.retriever.dense else 0,
            "reranker_loaded": context.agent.reranker.reranker is not None,
            "qa_enabled": settings.qa_enabled,
            "answer_model": settings.llm_model,
            "agent_model": settings.agent_model,
            "request_timeout": settings.request_timeout,
            "max_model_calls": settings.max_model_calls,
            "context_k": settings.context_k,
            "retrieval_k": settings.retrieval_k,
        }
        for scenario in scenarios:
            _, session = context.auth_dao.issue_session()
            owner = session["id"]
            cid = context.chat_dao.create_conversation(owner)["id"]
            for index, case in enumerate(scenario["turns"], 1):
                conversation = context.chat_dao.conversation(owner, cid)
                memory = context.memory_service.resolve(owner, conversation, case["question"])
                body = SimpleNamespace(conversation_id=cid, request_id=str(uuid.uuid4()),
                                       question=case["question"], mode=scenario["mode"])
                row = {"scenario": scenario["id"], "category": scenario["category"], "turn": index,
                       "mode": scenario["mode"], "question": case["question"], "goal": case["goal"],
                       "memory_before": {"source": memory.retrieved_from,
                                         "previous_question": memory.previous_question,
                                         "recent": [turn.model_dump() for turn in memory.recent]}}
                start = time.perf_counter()
                events = []
                try:
                    stream = await context.chat_service.chat(body, owner)
                    async for frame in stream:
                        if frame.startswith("data: "):
                            events.append(json.loads(frame[6:]))
                    result = next((e["data"] for e in events if e["type"] == "result"), None)
                    row["result"] = result
                    row["errors"] = [e for e in events if e["type"] == "error"]
                    row["completed"] = bool(events and events[-1]["type"] == "done" and result)
                    if result:
                        answer = result["answer"]
                        checks = {
                            "completed": row["completed"],
                            "expected_route": not case.get("expected_routes") or result["status"] in case["expected_routes"],
                            "required_content": not case.get("required_any") or any(s in answer for s in case["required_any"]),
                            "no_forbidden_claim": not any(s in answer for s in case.get("forbidden", [])),
                            "single_final_disclaimer": answer.endswith(DISCLAIMER) and answer.count(DISCLAIMER) == 1,
                            "no_mode_preface": not answer.startswith("探索模式"),
                            "model_budget": result["model_calls"] <= settings.max_model_calls,
                            "qa_excluded": all(e["document"]["source_type"] != "qa" for e in result["evidence"]),
                        }
                        row["checks"] = checks
                        row["contract_pass"] = all(checks.values())
                    else:
                        row["contract_pass"] = False
                    stored = context.chat_dao.conversation(owner, cid)["runs"]
                    row["persistence"] = {"runs": len(stored), "latest_status": stored[-1]["status"] if stored else None}
                except Exception as error:
                    row.update(completed=False, contract_pass=False, exception_type=type(error).__name__)
                row["end_to_end_ms"] = round((time.perf_counter() - start) * 1000)
                if prepare and row.get("result"):
                    row["outbound_candidates"] = [e["document"] for e in row["result"]["evidence"]]
                report["turns"].append(row)
                with progress.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(json.dumps({"scenario": scenario["id"], "turn": index, "question": case["question"],
                                  "status": (row.get("result") or {}).get("status"),
                                  "contract_pass": row["contract_pass"], "ms": row["end_to_end_ms"]}, ensure_ascii=False), flush=True)
        full = context.retriever.exploration_dense
        report["runtime"]["dense_exploration_documents"] = len(full.documents) if full else 0
    finally:
        context.close()
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        report["code_sha256_end"] = fingerprint()
        report["version_unchanged"] = report["code_sha256_end"] == start_hash
        report["turn_count"] = len(report["turns"])
        report["contract_pass_count"] = sum(row["contract_pass"] for row in report["turns"])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use configured model endpoints with synthetic dialogues")
    parser.add_argument("--prepare", action="store_true", help="Offline model-free answers; export candidate source text")
    parser.add_argument("--output", help="Separate report basename for online/degraded comparisons")
    args = parser.parse_args()
    if args.output and Path(args.output).name != args.output:
        parser.error("--output must be a filename basename")
    asyncio.run(run(args.llm, args.prepare, args.output))
