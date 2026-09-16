"""Fault injection on temporary fixtures; never stops real infrastructure."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from agent.QueryAnalyzer import QueryAnalyzer
from agent.RetrievalPlanner import RetrievalPlanner
from common.Settings import Settings
from evaluation.IndustrialEvaluationRunner import fingerprint
from memory.layers.RedisMemory import RedisMemory
from rag.entity.Evidence import Evidence
from rag.RerankerUtil import Reranker
from rag.service.RAGService import RAGService
from tests.test_contracts import Fixtures


async def run():
    Fixtures.setUpClass()
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "code_sha256": fingerprint(), "probes": []}
    try:
        settings, corpus = Fixtures.settings, Fixtures.corpus
        retriever = Fixtures.retriever
        retriever.dense = SimpleNamespace(search=Mock(side_effect=ConnectionError("simulated dense failure")))
        try:
            evidence = retriever.hybrid("高血压有什么症状")
            report["probes"].append({"name": "dense_runtime_failure", "passed": bool(evidence),
                                     "expectation": "向量运行失败时仍可用 BM25 结果并显式降级"})
        except Exception as error:
            report["probes"].append({"name": "dense_runtime_failure", "passed": False,
                                     "exception_type": type(error).__name__,
                                     "finding": "向量运行异常直接向外传播，未回退 BM25"})
        finally:
            retriever.dense = None
        analyzer = QueryAnalyzer(corpus)
        analysis = analyzer.analyze("高血压有哪些症状")
        ranker = Reranker(settings)
        ranker.reranker = SimpleNamespace(predict=Mock(side_effect=RuntimeError("simulated ranker failure")))
        ranked = ranker.rerank(analysis.query, [Evidence(document=corpus.reviewed[0])], analysis)
        report["probes"].append({"name": "reranker_runtime_failure", "passed": bool(ranked),
                                 "fallback_visible_in_warning": bool(ranker.warnings),
                                 "finding": "规则排序仍返回结果；运行时失败是否被可观察记录需单独判断"})
        graph = SimpleNamespace(driver=True, query=Mock(side_effect=ConnectionError("simulated graph failure")))
        plan = RetrievalPlanner(settings).plan(analysis, False)
        plan.use_graph = True
        _, _, observation = await RAGService(corpus, retriever, settings, graph).retrieve(analysis.query, analysis, plan)
        report["probes"].append({"name": "neo4j_runtime_failure", "passed": observation["graph_status"] == "local_fallback",
                                 "observation": observation})
        cache = RedisMemory(settings)
        cache.client = SimpleNamespace(get=Mock(side_effect=ConnectionError("simulated redis failure")))
        value = cache.get("synthetic-owner", "synthetic-conversation", "empty")
        report["probes"].append({"name": "redis_runtime_failure", "passed": value is None and cache.status == "unavailable"})
    finally:
        Fixtures.tearDownClass()
        path = Settings().reports_dir / "service-faults.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
