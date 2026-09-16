"""User-reported failures and paraphrases: topic, usefulness, length and synthesis regressions."""

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agent.MedicalAgent import MedicalAgent
from common.Settings import Settings
from rag.corpus.MedicalCorpus import MedicalCorpus
from rag.retriever.HybridRetriever import HybridRetriever


async def run(models=False, llm=False, prepare=False, cases_path=None, output_name="answer-quality"):
    settings = Settings()
    if not models:
        settings = settings.model_copy(update={"embedding_model": "", "reranker_model": ""})
    if not llm or prepare:
        settings = settings.model_copy(update={"provider": "extractive"})
    corpus = MedicalCorpus(settings.data_dir)
    agent = MedicalAgent(corpus, HybridRetriever(corpus, settings), settings)
    source = Path(cases_path) if cases_path else Path(__file__).with_name("quality_cases.json")
    cases = json.loads(source.read_text(encoding="utf-8"))
    case_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    code = hashlib.sha256()
    for folder in ["agent", "rag", "ai", "common"]:
        for path in sorted((Path(__file__).resolve().parents[1] / folder).rglob("*.py")):
            code.update(path.name.encode())
            code.update(path.read_bytes())
    progress = settings.reports_dir / (output_name + ".progress.jsonl")
    progress.write_text("", encoding="utf-8")
    rows = []
    for case in cases:
        for mode in case["modes"]:
            expected = case.get("mode_expect", {}).get(mode, case["expected"])
            result = await agent.run(
                case["question"],
                mode=mode,
                run_id="quality-" + str(len(rows)),
                previous_question=case.get("previous_question", ""),
            )
            checks = {
                "expected_route": result.status == expected,
                "answers_topic": expected != "answered"
                or all(any(term in result.answer for term in group) for group in case["required_groups"]),
                "no_reported_failure": not any(term in result.answer for term in case["forbidden"])
                and not any(
                    re.search(pattern, result.answer) for pattern in case.get("forbidden_patterns", [])
                ),
                "concise": len(result.answer) <= 800,
                "synthesis": not llm
                or expected != "answered"
                or result.generation_mode == "grounded_synthesis",
                "no_qa": all(ev.document.source_type != "qa" for ev in result.evidence),
                "citation_gate": result.status != "answered"
                or bool(result.answer_grade and result.answer_grade.passed),
            }
            if case.get("check_all_routes"):
                checks["useful_boundary"] = all(
                    any(term in result.answer for term in group) for group in case["required_groups"]
                )
            if case.get("previous_question"):
                checks["contextualized"] = result.analysis.contextualized
            row = {
                "question": case["question"],
                "mode": mode,
                "checks": checks,
                "passed": all(checks.values()),
                "status": result.status,
                "answer": result.answer,
                "analysis": result.analysis.model_dump(),
                "evidence_grade": result.evidence_grade.model_dump() if result.evidence_grade else None,
                "warnings": result.warnings,
                "generation_mode": result.generation_mode,
                "answer_grade": result.answer_grade.model_dump() if result.answer_grade else None,
                "model_calls": result.model_calls,
                "duration_ms": result.duration_ms,
                "sources": [ev.document.id for ev in result.evidence],
                "evidence": [
                    {
                        "id": ev.document.id,
                        "title": ev.document.title,
                        "facet": ev.document.facet,
                        "relevance": ev.relevance,
                        "url": ev.document.source_url,
                        "review_status": ev.document.review_status,
                    }
                    for ev in result.evidence
                ],
                "repairs": [event.detail for event in result.trace if event.step == "repair_answer"],
            }
            rows.append(row)
            with progress.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if prepare:
                row["outbound_documents"] = [
                    {
                        "id": ev.document.id,
                        "source_type": ev.document.source_type,
                        "source_url": ev.document.source_url,
                        "title": ev.document.title,
                        "text": ev.document.text,
                    }
                    for ev in result.evidence
                    if result.evidence_grade and ev.document.id in result.evidence_grade.eligible_ids
                ]
            print(
                json.dumps(
                    {
                        "case": len(rows),
                        "question": case["question"],
                        "mode": mode,
                        "passed": row["passed"],
                        "checks": checks,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_version": corpus.manifest["version"],
        "case_sha256": case_sha256,
        "case_definitions": cases,
        "code_sha256": code.hexdigest(),
        "llm": llm,
        "local_models": models,
        "runtime": {
            "dense_loaded": agent.retriever.dense is not None,
            "reranker_loaded": agent.reranker.reranker is not None,
            "qa_enabled": settings.qa_enabled,
            "answer_model": settings.llm_model,
            "agent_model": settings.agent_model,
            "retrieval_k": settings.retrieval_k,
            "context_k": settings.context_k,
            "max_model_calls": settings.max_model_calls,
            "max_iterations": settings.max_iterations,
        },
        "case_count": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "cases": rows,
        "scope": "用户反馈问题及同义改写的工程回归；词项、篇幅和模型检查不能替代人工医学正确性评审。",
    }
    filename = output_name + ("-payload-preview.json" if prepare else ".json")
    (settings.reports_dir / filename).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--llm", action="store_true", help="Use configured answer and review model APIs")
    parser.add_argument("--cases", help="Synthetic test cases JSON; never use patient records")
    parser.add_argument("--output", default="answer-quality", help="Report basename")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Offline only: export regression questions and eligible source text for inspection",
    )
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        parser.error("--output must be a filename basename")
    asyncio.run(run(args.models, args.llm, args.prepare, args.cases, args.output))
