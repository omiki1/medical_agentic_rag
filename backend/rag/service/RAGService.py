import asyncio

from agent.EvidenceGrader import EvidenceGrader
from agent.EvidencePolicy import EvidencePolicy
from agent.QueryAnalyzer import FACET_RELATIONS
from agent.QueryTopics import QueryTopics

from rag.entity.Evidence import Evidence
from rag.fusion.EvidenceFusion import fuse
from rag.RerankerUtil import Reranker
from rag.retriever.GraphRetriever import GraphRetriever


class RAGService:
    """Fixed retrieval → fusion → reranking → evidence gate, usable without an Agent."""

    def __init__(self, corpus, retriever, settings, graph=None):
        self.retriever, self.settings, self.graph = retriever, settings, graph
        self.corpus = corpus
        self.reviewed_entities = {doc.entity: doc for doc in corpus.reviewed}
        self.reranker = Reranker(settings)
        self.graph_retriever = GraphRetriever(corpus)
        self.grader = EvidenceGrader(settings.max_source_age_days)

    async def retrieve(self, query, analysis, plan, *, mode="hybrid", hypothesis=""):
        if mode == "bm25":
            baseline = await asyncio.to_thread(self.retriever.bm25.search, query, self.settings.retrieval_k)
        elif mode == "dense":
            baseline = (
                await asyncio.to_thread(self.retriever.dense.search, query, self.settings.retrieval_k)
                if self.retriever.dense
                else []
            )
        else:
            baseline = await asyncio.to_thread(self.retriever.hybrid, query, None, analysis.mode)
        graph_evidence = (
            self.graph_retriever.retrieve(analysis, include_unreviewed=analysis.mode == "exploratory")
            if plan.use_graph
            else []
        )
        observation = {
            "candidates": len(baseline),
            "graph_candidates": len(graph_evidence),
            "graph_status": "unused",
        }
        if plan.use_graph:
            observation["graph_status"] = "local_provenance"
            if self.graph and self.graph.driver:
                try:
                    relations = [r for f in analysis.facets for r in FACET_RELATIONS.get(f, [])]
                    rows = await asyncio.to_thread(self.graph.query, analysis.entities, relations)
                    paths = {(r["subject"], r["relation"], r["object"]) for r in rows}
                    for ev in graph_evidence:
                        if any(tuple(p) in paths for p in ev.graph_paths):
                            ev.methods.append("neo4j_verified")
                    observation.update(graph_status="neo4j_connected", graph_rows=len(rows))
                except Exception as error:
                    observation.update(graph_status="local_fallback", graph_error=type(error).__name__)
        hypothetical = []
        if hypothesis and self.retriever.dense:
            hypothetical = await asyncio.to_thread(self.retriever.dense.search, hypothesis, 10, "hyde")
            observation.update(hyde_candidates=len(hypothetical), hypothesis_is_evidence=False)
        anchor_ids = []
        for name, representative in self.reviewed_entities.items():
            if any(EvidencePolicy.entity_matches(representative, entity) for entity in analysis.entities):
                anchor_ids.extend(self.corpus.by_entity.get(name, []))
        for entity in dict.fromkeys(
            [*analysis.entities, *(term for group in analysis.topic_groups for term in group)]
        ):
            anchor_ids.extend(self.corpus.by_entity.get(entity, []))
        anchors = [
            Evidence(document=self.corpus.documents[doc_id], methods=["entity_lookup"])
            for doc_id in dict.fromkeys(anchor_ids)
            if (
                analysis.mode == "exploratory"
                or self.corpus.documents[doc_id].review_status == "source_checked"
            )
            and any(
                QueryTopics.broad_overview(analysis)
                or EvidencePolicy.facet_matches(self.corpus.documents[doc_id], f, analysis.mode)
                for f in analysis.facets
            )
        ]
        anchors.sort(
            key=lambda ev: (
                ev.document.facet not in analysis.facets,
                ev.document.review_status != "source_checked",
                ev.document.id,
            )
        )
        anchors = anchors[: self.settings.retrieval_k]
        evidence = fuse(
            baseline,
            graph_evidence,
            hypothetical,
            anchors,
            k=self.settings.retrieval_k + 24,
            weights={"hyde": 0.7},
        )
        before_topic = len(evidence)
        stage_counts = {
            "fused": before_topic,
            "graph": len(graph_evidence),
            "hyde": len(hypothetical),
            "anchor": len(anchors),
        }
        kept, exclusions = [], []
        for ev in evidence:
            d = ev.document
            if not EvidencePolicy.topic_matches(d, analysis):
                exclusions.append({"doc": d.id, "reason": "topic_mismatch"})
                continue
            if EvidencePolicy.disease_specific_symptom_mismatch(d, analysis):
                exclusions.append({"doc": d.id, "reason": "disease_specific_symptom"})
                continue
            if not EvidencePolicy.population_matches(d, analysis):
                exclusions.append({"doc": d.id, "reason": "population_mismatch"})
                continue
            if EvidencePolicy.unreliable_claims(d):
                exclusions.append({"doc": d.id, "reason": "unreliable_claims"})
                continue
            kept.append(ev)
        evidence = kept
        observation.update(
            topic_rejected=len(exclusions),
            exclusion_reasons={
                reason: sum(1 for x in exclusions if x["reason"] == reason)
                for reason in {x["reason"] for x in exclusions}
            },
            stage_counts=stage_counts,
            topic_groups=analysis.topic_groups,
            anchor_candidates=len(anchors),
        )
        evidence = await asyncio.to_thread(self.reranker.rerank, analysis.query, evidence, analysis)
        self.order_evidence(evidence, analysis)
        grade = self.grader.grade(analysis, evidence)
        observation.update(
            evidence=len(evidence),
            eligible=len(grade.eligible_ids),
            eligible_reasons=grade.reasons,
            coverage=grade.coverage,
            ranker="cross_encoder" if self.reranker.last_predictions_used else "coverage_heuristic",
            ranker_loaded=self.reranker.reranker is not None,
            ranker_predictions_used=self.reranker.last_predictions_used,
            ranker_error=self.reranker.last_predictions_error,
        )
        return evidence, grade, observation

    @staticmethod
    def order_evidence(evidence, analysis):
        """Keep topic priority while preserving descending relevance and display identities."""
        if analysis.entities:
            evidence.sort(
                key=lambda ev: (
                    not any(
                        EvidencePolicy.entity_matches(ev.document, entity) for entity in analysis.entities
                    ),
                    -QueryTopics.score(ev.document, analysis.topic_groups),
                    -ev.relevance,
                )
            )
        else:
            # No entity: relevance is the strongest signal (cross-encoder already scored the
            # query-document pairs), with fine-grained theme score as a topic tie-breaker.
            # Sorting ONLY by coverage here made rerank a no-op whenever several documents
            # each contained one shared word (e.g. "上吐下泻" in both 肠胃炎 and 头痛 pages).
            evidence.sort(
                key=lambda ev: (
                    -ev.relevance,
                    -QueryTopics.score(ev.document, analysis.topic_groups),
                    ev.document.id,
                )
            )
        for rank, ev in enumerate(evidence, 1):
            ev.rank, ev.citation_id = rank, f"E{rank}"
