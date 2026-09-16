import re
from datetime import date

from agent.entity.AgentState import EvidenceGrade
from agent.EvidencePolicy import EvidencePolicy
from agent.QueryAnalyzer import FACET_LABELS
from agent.QueryTopics import QueryTopics


class EvidenceGrader:
    def __init__(self, max_age_days=1095):
        self.max_age_days = max_age_days

    def grade(self, analysis, evidence, today=None):
        today = today or date.today()
        eligible, reasons = [], []
        definition_like = bool(re.search(r"是什么|什么是|定义|概念", analysis.original))
        pubmed_present = False
        for ev in evidence:
            d = ev.document
            if d.review_status == "withdrawn":
                continue
            if EvidencePolicy.unreliable_claims(d):
                reasons.append("历史资料含明显不可靠的治疗或治愈宣称，已排除")
                continue
            pubmed_doc = EvidencePolicy.pubmed_literature(d, analysis)
            if analysis.mode == "authoritative" and d.review_status != "source_checked" and not pubmed_doc:
                reasons.append("存在尚未核验来源的资料")
                continue
            if pubmed_doc:
                pubmed_present = True
            if analysis.mode == "authoritative" and not pubmed_doc and (
                not d.checked_at
                or (
                    not d.published_at
                    and d.date_provenance
                    not in {"publication_unknown_collector_fallback_removed", "publication_not_extracted"}
                )
            ):
                reasons.append("资料缺少发布日期或核验日期")
                continue
            age = (today - d.published_at).days if d.published_at else None
            checked_age = (today - d.checked_at).days if d.checked_at else None
            if (
                (age is not None and age < 0)
                or (checked_age is not None and checked_age < 0)
                or (
                    analysis.mode == "authoritative"
                    and not pubmed_doc
                    and (
                        (age is not None and age > self.max_age_days)
                        or (checked_age is not None and checked_age > self.max_age_days)
                    )
                )
            ):
                reasons.append("资料日期不满足当前时效规则")
                continue
            if not EvidencePolicy.topic_matches(d, analysis):
                reasons.append("资料没有匹配问题的实质主题")
                continue
            if EvidencePolicy.unsafe_unreviewed_dose(d):
                reasons.append("待复核资料中的剂量建议未作为回答依据")
                continue
            if ev.relevance < 0.48 and not pubmed_doc:
                continue
            eligible.append(ev)
        if analysis.facets == ["overview"] and definition_like:
            eligible = [
                ev for ev in eligible if EvidencePolicy.facet_matches(ev.document, "overview", analysis.mode)
            ]
            required_facets = ["overview"]
        elif analysis.facets == ["overview"]:
            # Broad questions that matched no facet word (e.g. "晚上总做梦睡不好是正常的吗？")
            # should not be restricted to overview-only docs: keeping the dense cause/prevention
            # material prevents off-topic answers from unrelated fact sheets that merely share
            # one common word (e.g. "sleep" in a PTSD self-care page).
            required_facets = []
        else:
            required_facets = analysis.facets
        required = [(entity, facet) for entity in (analysis.entities or [None]) for facet in required_facets]
        missing = []
        pubmed_entities = {
            ev.document.entity
            for ev in eligible
            if ev.document.source_type == "research"
            and EvidencePolicy.pubmed_literature(ev.document, analysis)
            and ev.document.entity
        }
        for entity, facet in required:
            if any(
                (entity is None or EvidencePolicy.entity_matches(ev.document, entity))
                and EvidencePolicy.facet_matches(ev.document, facet, analysis.mode)
                for ev in eligible
            ):
                continue
            # For a "latest/今年" question, PubMed research abstracts about the asked
            # entity count as covering its current knowledge, even though an English
            # abstract rarely carries the Chinese facet label. Entity identity is still
            # required (a paper about something else cannot fill the gap).
            if (
                analysis.wants_latest
                and entity in pubmed_entities
            ):
                continue
            missing.append(f"{entity or '所述问题'}的{FACET_LABELS.get(facet, facet)}")
        for group in analysis.topic_groups:
            if not any(QueryTopics.coverage(ev.document, [group]) for ev in eligible):
                missing.append(group[0] + "的相关资料")
        # Special populations, current recommendations and combined-condition prescribing
        # need explicit scoped evidence; general fact sheets cannot satisfy these.
        general_definition = (
            analysis.facets == ["overview"]
            and definition_like
            and not analysis.wants_latest
            and not analysis.personal_treatment
        )
        if analysis.constraints and not general_definition:
            for constraint in analysis.constraints:
                if constraint == "最新资料" and pubmed_present:
                    # PubMed research clues satisfy the "latest" ask; they are shown as
                    # research literature needing professional interpretation, not as
                    # verified guidance. Other constraints (孕/儿等) still need scoped docs.
                    continue
                missing.append(f"{constraint}的专门证据")
        if analysis.personal_treatment:
            missing.append("个人用药决策所需的完整临床信息与专业评估")
        coverage = (len(required) - min(len(required), len(missing))) / max(1, len(required))
        if not required and not missing:
            coverage = 1.0
        if not eligible and not missing:
            missing.append("可验证的相关来源")
        if analysis.mode == "exploratory":
            reasons.append("探索模式：允许待复核来源与不完整覆盖，不保证医学正确或最新")
        personal_scope = analysis.personal_treatment or (
            bool(analysis.constraints)
            and any(f in {"medication", "treatment"} for f in analysis.facets)
            and any(
                c not in {"最新资料"}
                for c in analysis.constraints
            )
        )
        return EvidenceGrade(
            sufficient=bool(eligible)
            and not personal_scope
            and (not missing or analysis.mode == "exploratory"),
            coverage=coverage,
            missing=list(dict.fromkeys(missing)),
            reasons=list(dict.fromkeys(reasons)),
            eligible_ids=[ev.document.id for ev in eligible],
        )
