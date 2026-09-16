import re

from agent.entity.AgentState import AnswerGrade
from agent.EvidencePolicy import EvidencePolicy


class AnswerGrader:
    """Validate source spans, citation identity and requested facet coverage.

    This deliberately does not claim to estimate clinical truth or hallucination rate.
    Natural explanations remain pending until the independent semantic review.
    """

    def grade(self, draft, evidence, analysis, *, synthesized=False):
        by_id = {ev.document.id: ev for ev in evidence}
        errors, cited = [], set()
        for claim in draft.claims:
            if EvidencePolicy.prescribing_detail(claim.text) and not any(
                by_id[i].document.review_status == "source_checked" for i in claim.evidence_ids if i in by_id
            ):
                errors.append("具体治疗或检查频次建议缺少已核验来源")
            if len(claim.evidence_ids) != len(claim.quotes):
                errors.append("引用与原文片段未一一对应")
                continue
            for doc_id, quote in zip(claim.evidence_ids, claim.quotes):
                ev = by_id.get(doc_id)
                if (
                    not ev
                    or ev.document.review_status == "withdrawn"
                    or (
                        analysis.mode == "authoritative"
                        and ev.document.review_status != "source_checked"
                        and not EvidencePolicy.pubmed_literature(ev.document, analysis)
                    )
                ):
                    errors.append("引用指向不可用证据")
                elif quote not in ev.document.text or len(quote.strip()) < 4:
                    errors.append("引用片段不在来源原文中")
                else:
                    cited.add(doc_id)
            # Exact extract mode: no model-written medical inference can pass this gate.
            if not synthesized and claim.text != "".join(claim.quotes):
                errors.append("出现不受原文支持的改写或推论")
        relevant = bool(cited) and all(
            EvidencePolicy.topic_matches(by_id[i].document, analysis) for i in cited
        )
        definition_like = bool(re.search(r"是什么|什么是|定义|概念", analysis.original))
        broad_overview = analysis.facets == ["overview"] and not definition_like
        if broad_overview:
            # Same rule as EvidenceGrader: a question like "晚上总做梦睡不好是正常的吗？"
            # matched no facet word, so any relevant facet (cause/prevention/...) counts as
            # complete coverage. Requiring an overview doc here would reject the very
            # insomnia cause/prevention material that actually answers the question.
            complete = bool(cited)
        else:
            complete = all(
                any(
                    (entity is None or EvidencePolicy.entity_matches(by_id[i].document, entity))
                    and EvidencePolicy.facet_matches(by_id[i].document, facet, analysis.mode)
                    for i in cited
                )
                for entity in (analysis.entities or [None])
                for facet in analysis.facets
            )
        if analysis.mode == "exploratory":
            complete = bool(cited)
        if not relevant:
            errors.append("答案与已识别的疾病不匹配")
        if not complete:
            errors.append("答案遗漏问题要求的证据维度")
        return AnswerGrade(
            grounded=not errors,
            relevant=relevant,
            complete=complete,
            feedback=list(dict.fromkeys(errors)),
            verification="semantic_review_pending" if synthesized else "exact_extract",
            total_claims=len(draft.claims),
        )
