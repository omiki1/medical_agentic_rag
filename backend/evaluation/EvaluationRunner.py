import argparse
import asyncio
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.MedicalAgent import MedicalAgent
from common.Settings import Settings
from rag.corpus.MedicalCorpus import MedicalCorpus
from rag.fusion.EvidenceFusion import fuse
from rag.retriever.HybridRetriever import HybridRetriever


class EvaluationRunner:
    """Identical questions and qrels across ablations. Failed cases stay in the report."""

    def __init__(self, settings, real_models=False, llm=False):
        self.settings = settings.model_copy(update={"provider": settings.provider if llm else "extractive"})
        if not real_models:
            self.settings = self.settings.model_copy(update={"embedding_model": "", "reranker_model": ""})
        self.corpus = MedicalCorpus(settings.data_dir)
        self.retriever = HybridRetriever(self.corpus, self.settings)
        self.agent = MedicalAgent(self.corpus, self.retriever, self.settings)
        self.cases_path = Path(__file__).with_name("cases.json")
        self.cases = json.loads(self.cases_path.read_text(encoding="utf-8"))

    @staticmethod
    def metrics(evidence, gold):
        ids = [ev.document.id for ev in evidence[:5]]
        hits = [int(doc_id in gold) for doc_id in ids]
        recall = len(set(ids) & gold) / len(gold)
        reciprocal = next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0)
        dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
        ideal = sum(1 / math.log2(i + 2) for i in range(min(5, len(gold))))
        return {"recall_at_5": recall, "mrr": reciprocal, "ndcg_at_5": dcg / ideal}

    def retrieve(self, name, case):
        query = case["question"]
        analysis = self.agent.analyzer.analyze(query)
        if name == "BM25":
            return self.retriever.bm25.search(query, 16)
        if name == "Dense":
            return self.retriever.dense.search(query, 16)
        evidence = self.retriever.hybrid(query)
        if "Graph" in name:
            evidence = fuse(evidence, self.agent.rag.graph_retriever.retrieve(analysis))
        if "Rerank" in name:
            evidence = self.agent.reranker.rerank(query, evidence, analysis)
        return evidence

    async def run(self):
        rows, comparisons, detailed = [], [], []
        names = ["BM25"]
        if self.retriever.dense:
            names.append("Dense")
        names += ["RRF", "RRF + Graph", "RRF + Graph + Rerank"]
        retrieval_cases = []
        for case in self.cases:
            if not case.get("entity"):
                continue
            gold = {
                doc.id
                for doc in self.corpus.reviewed
                if doc.entity == case["entity"] and doc.facet == case["facet"]
            }
            if not gold:
                raise ValueError(f"Invalid evaluation qrel: {case['entity']}/{case['facet']}")
            retrieval_cases.append((case, gold))
        for name in names:
            measurements = []
            for case, gold in retrieval_cases:
                start = time.perf_counter()
                evidence = self.retrieve(name, case)
                measurement = self.metrics(evidence, gold)
                measurement["latency_ms"] = (time.perf_counter() - start) * 1000
                measurements.append(measurement)
                detailed.append(
                    {
                        "configuration": name,
                        "question": case["question"],
                        "gold": sorted(gold),
                        "retrieved": [e.document.id for e in evidence[:5]],
                        **measurement,
                    }
                )
            rows.append(
                {
                    "name": name,
                    "note": "真实本地模型"
                    if name == "Dense" or ("Rerank" in name and self.agent.reranker.reranker)
                    else "固定语料工程回归",
                    **{key: statistics.mean(row[key] for row in measurements) for key in measurements[0]},
                }
            )
        cases = []
        for fixed, name in [(True, "固定编排 RAG"), (False, "编排 RAG + 受限 Agent")]:
            results = []
            for i, case in enumerate(self.cases):
                result = await self.agent.run(
                    case["question"],
                    run_id=f"eval-{fixed}-{i}",
                    fixed=fixed,
                    mode=case.get("mode", "authoritative"),
                )
                print(f"evaluation {name}: {i + 1}/{len(self.cases)} {result.status}", flush=True)
                passed = result.status == case["expected"]
                results.append(
                    {
                        "passed": passed,
                        "status": result.status,
                        "iterations": result.iterations,
                        "latency_ms": result.duration_ms,
                        "model_calls": result.model_calls,
                    }
                )
                if not fixed:
                    cases.append(
                        {
                            "question": case["question"],
                            "mode": case.get("mode", "authoritative"),
                            "expected": case["expected"],
                            "actual": result.status,
                            "passed": passed,
                            "safety": case.get("safety", False),
                        }
                    )
            comparisons.append(
                {
                    "name": name,
                    "routing_accuracy": statistics.mean(int(r["passed"]) for r in results),
                    "mean_rounds": statistics.mean(r["iterations"] for r in results),
                    "mean_latency_ms": statistics.mean(r["latency_ms"] for r in results),
                    "model_calls": sum(r["model_calls"] for r in results),
                }
            )
        safety = [case for case in cases if case["safety"]]
        report = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "case_count": len(cases),
            "retrieval_case_count": len(retrieval_cases),
            "source_count": len({d.source_id for d in self.corpus.reviewed}),
            "routing_accuracy": statistics.mean(int(c["passed"]) for c in cases),
            "safety_pass_rate": statistics.mean(int(c["passed"]) for c in safety),
            "corpus_version": self.corpus.manifest["version"],
            "qa_generation": self.retriever.qa.manifest.get("generation"),
            "case_sha256": hashlib.sha256(self.cases_path.read_bytes()).hexdigest(),
            "dense": bool(self.retriever.dense),
            "reranker": bool(self.agent.reranker.reranker),
            "provider": self.settings.provider,
            "ablations": rows,
            "pipelines": comparisons,
            "cases": cases,
            "scope": "人工编写的小规模工程回归集；核对路由、引用和检索表现，不代表临床诊疗准确率。",
            "limitations": "回归用例仅覆盖来源集合的一小部分；缺乏医生标注和独立外部验证。新增 WHO 扩大了来源范围，不能据此推定全库正确。规则与用例共同演进，属于开发回归集。",
        }
        output = self.settings.reports_dir
        output.mkdir(parents=True, exist_ok=True)
        (output / "evaluation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (
            output
            / ("evaluation-live.json" if self.settings.provider == "compatible" else "evaluation-local.json")
        ).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "retrieval-details.json").write_text(
            json.dumps(detailed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in [
                        "case_count",
                        "routing_accuracy",
                        "safety_pass_rate",
                        "dense",
                        "reranker",
                        "pipelines",
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true", help="Use configured local embedding and reranker")
    parser.add_argument("--llm", action="store_true", help="Explicitly enable paid configured model calls")
    args = parser.parse_args()
    asyncio.run(EvaluationRunner(Settings(), args.models, args.llm).run())
