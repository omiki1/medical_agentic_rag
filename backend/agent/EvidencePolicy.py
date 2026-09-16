import re

from agent.QueryTopics import QueryTopics


class EvidencePolicy:
    # Symptom-level entities (rather than disease names) must not lock retrieval to
    # one exact term: "腹泻" should still surface 肠胃炎/食物中毒/WHO diarrhoeal
    # material via coverage, not just documents whose entity is literally 腹泻.
    SYMPTOM_ENTITIES = frozenset(
        {
            "头痛", "头疼", "腹痛", "肚子疼", "胃痛", "胃疼", "失眠", "咳嗽", "发热", "发烧",
            "眩晕", "头晕", "腹泻", "拉肚子", "呕吐", "恶心", "便秘", "乏力", "心悸", "心慌",
            "皮疹", "红疹", "口渴", "多尿", "体重下降", "消瘦",
        }
    )

    @staticmethod
    def prescribing_detail(text):
        """Details that need checked sources rather than an unreviewed historical passage."""
        return bool(
            re.search(
                r"激素替代|药物治疗|抑制骨吸收|促进骨形成|长期.{0,8}补钙|"
                r"(?:每年|每月|每周).{0,14}(?:检查|检测|复查)|"
                r"(?:血压|血糖).{0,20}(?:控制在|目标|低于|小于|＜|<).{0,5}\d|"
                r"\d+(?:\.\d+)?\s*(?:mg|毫克|微克)|每天\s*\d+\s*片",
                text,
                re.I,
            )
        )

    @staticmethod
    def unreliable_claims(document):
        """Quarantine explicit cure/pH misinformation in historical text, without deleting it.

        This catches known defects, not every possible medical error.
        """
        return document.review_status != "source_checked" and bool(
            re.search(
                r"(?:癌|肿瘤).{0,35}(?:只能|不能).{0,20}(?:酸性|弱碱性)|"
                r"(?:酸性|弱碱性).{0,65}(?:治好|治愈|不会得|不能扩展)|包治百病|保证治愈",
                document.text,
                re.I,
            )
        )

    @staticmethod
    def population_matches(document, analysis):
        subject = document.entity + " " + document.title
        for pattern in [r"小儿|儿童|婴儿|新生儿", r"孕妇|孕期|妊娠|哺乳"]:
            if re.search(pattern, subject) and not re.search(
                pattern + r"|孩子" if "儿童" in pattern else pattern, analysis.query
            ):
                return False
        return True

    @staticmethod
    def topic_matches(document, analysis):
        if analysis.entities and any(
            EvidencePolicy.entity_matches(document, entity) for entity in analysis.entities
        ):
            return True
        # Symptom-level entities (rather than disease names) must not lock retrieval to
        # one exact term: "腹泻" should still surface 肠胃炎/食物中毒/WHO diarrhoeal
        # material via coverage, not just documents whose entity is literally 腹泻.
        symptom_entities = EvidencePolicy.SYMPTOM_ENTITIES
        if analysis.entities and not any(
            entity in symptom_entities for entity in analysis.entities
        ):
            return False
        return QueryTopics.coverage(document, analysis.topic_groups) > 0

    @staticmethod
    def disease_specific_symptom_mismatch(document, analysis):
        """A single disease's symptom section is not evidence for a general symptom question.

        The corpus keeps one "symptom" section per disease. For a question that only
        describes a symptom ("小孩发烧38.5度怎么处理"), the symptom lists of unrelated
        diseases (呼吸道合胞病毒 / 日本脑炎 / B组链球菌) each contain 发热, so they passed the
        topic-coverage test and were cited as if they were about the question — the
        "飘逸" failure mode in its residual form.

        Such a document is kept only when either:
          * the question itself raises that disease (entities, aliases, or literal text), or
          * the document's own entity is the symptom being asked about
            (query 拉肚子 must keep the 腹泻 symptom page).

        Only authoritative mode is filtered: exploratory mode is explicitly a wider net.
        """
        if analysis.mode != "authoritative" or document.facet != "symptom":
            return False
        entity = document.entity
        if not entity or entity in EvidencePolicy.SYMPTOM_ENTITIES:
            return False
        if any(EvidencePolicy.entity_matches(document, term) for term in analysis.entities):
            return False
        return entity not in (analysis.query or "")

    @staticmethod
    def entity_matches(document, entity):
        return (
            document.entity == entity
            or entity in document.aliases
            or any(
                entity.lower() in names and document.entity.lower() in names
                for names in QueryTopics.NAMED_SYNONYMS
            )
            or (
                document.source_type == "public_health"
                and bool(
                    re.search(
                        r"(?:^|[和与、，（）() ])" + re.escape(entity) + r"(?:$|病|症|炎|性|[和与、，（）() ])",
                        document.entity,
                    )
                )
            )
            or (document.source_type == "qa" and entity in document.title + document.text)
        )

    @staticmethod
    def facet_matches(document, facet, mode):
        return (
            document.facet == facet
            or facet == "association"
            or (
                facet == "cause"
                and bool(
                    re.search(
                        r"原因|病因|引起|导致|诱因|遗传|风险因素|cause|trigger|risk factor",
                        document.text,
                        re.I,
                    )
                )
            )
        )

    @staticmethod
    def unsafe_unreviewed_dose(document):
        return document.review_status != "source_checked" and bool(
            re.search(
                r"\d+(?:\.\d+)?\s*(?:mg|毫克|微克)|每天\s*\d+\s*片|自行停药|擅自停药", document.text, re.I
            )
        )

    @staticmethod
    def pubmed_literature(document, analysis):
        """PubMed research abstracts may be used as *additional* evidence for
        'latest/今年' questions, in both modes. They are never marked source_checked:
        the grader keeps treating them as research clues requiring professional
        interpretation, and they cannot satisfy medication/dose guidance on their own.
        """
        return (
            document.source_type == "research"
            and document.review_status != "source_checked"
            and analysis.wants_latest
        )
