import re

from rag.BM25Retriever import tokenize


class QueryTopics:
    """Medical concepts guide retrieval; symptom concepts never imply a diagnosis."""

    NAMED_SYNONYMS = [
        ("甲减", "甲状腺功能减退症", "甲状腺功能减退"),
        ("登革热", "dengue", "登革热和重症登革热", "dengue and severe dengue"),
    ]
    GROUPS = [
        ["登革热", "dengue", "dengue and severe dengue"],
        ["睡眠", "失眠", "入睡", "早醒", "睡不着", "睡不好", "睡觉", "insomnia", "sleep"],
        ["头痛", "头疼", "偏头痛", "headache", "migraine"],
        ["腹痛", "肚子疼", "肚子痛", "胃痛", "胃疼", "腹胀", "胃胀", "胀气", "abdominal pain", "stomach ache"],
        ["血糖", "高血糖", "低血糖", "糖尿病", "blood sugar", "glucose", "diabetes"],
        ["血压", "高血压", "低血压", "blood pressure", "hypertension"],
        ["甲亢", "甲状腺功能亢进", "hyperthyroidism"],
        ["甲减", "甲状腺功能减退", "甲状腺功能减退症", "hypothyroidism"],
        ["头晕", "眩晕", "晕乎乎", "眼前发黑", "体位性", "dizziness"],
        ["乏力", "疲劳", "没精神", "疲倦", "没劲", "fatigue"],
        ["焦虑", "紧张", "anxiety"],
        ["抑郁", "情绪低落", "depression"],
        ["心悸", "心慌", "手抖", "palpitation"],
        ["口渴", "多饮", "thirst"],
        ["多尿", "尿多", "排尿增多", "尿频", "frequent urination"],
        ["体重下降", "体重减轻", "消瘦", "weight loss"],
        ["咳嗽", "cough"],
        ["发热", "发烧", "fever"],
        ["腹泻", "拉肚子", "拉稀", "窜稀", "闹肚子", "上吐下泻", "水样便", "跑厕所", "肠鸣", "diarrhoea", "diarrhea"],
        ["便秘", "constipation"],
        ["恶心", "呕吐", "反胃", "上吐下泻", "nausea", "vomiting"],
        ["反酸", "烧心", "嗳气", "acid reflux", "heartburn"],
        ["皮疹", "红疹", "红疙瘩", "瘙痒", "rash"],
        ["过敏", "allergy"],
        ["肥胖", "超重", "obesity"],
    ]
    GENERIC = re.compile(
        r"是什么|什么是|有哪些|有什么|怎么办|怎么|如何|为什么|可能|引起|导致|造成|原因|病因|关系|问题|"
        r"症状|表现|预防|治疗|检查|介绍|科普|资料|请问|请告诉我|想问|想了解|了解|能够|可以|应该|的|了|吗|呢|与|和|是"
    )

    @classmethod
    def groups(cls, query, entities):
        lowered = query.lower()
        found = [group for group in cls.GROUPS if any(term in lowered for term in group)]
        if entities:
            # Only add explicit named entities, never infer disease from a symptom.
            found.extend([[entity] for entity in entities if not any(entity in group for group in found)])
        if not found:
            topic = cls.GENERIC.sub(" ", query)
            found = [[word] for word in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", topic)][:6]
        return found

    @staticmethod
    def contains(text, terms):
        lowered = text.lower()
        return any(
            bool(re.search(r"\b" + re.escape(term) + r"\b", lowered)) if term.isascii() else term in lowered
            for term in terms
        )

    @classmethod
    def coverage(cls, document, groups):
        if not groups:
            return 0.0
        text = " ".join([document.entity, *document.aliases, document.title, document.text])
        return sum(cls.contains(text, group) for group in groups) / len(groups)

    @classmethod
    def subject_coverage(cls, document, groups):
        if not groups:
            return 0.0
        subject = " ".join([document.entity, *document.aliases, document.title])
        return sum(cls.contains(subject, group) for group in groups) / len(groups)

    @staticmethod
    def broad_overview(analysis):
        return analysis.facets == ["overview"] and not re.search(
            r"是什么|什么是|什么叫|定义|概念", analysis.original
        )

    @classmethod
    def score(cls, document, groups):
        """Fine-grained theme fit: covered groups earn 1.0 plus a per-term bonus.

        Keeps documents that actually mention the question's concepts ahead of
        broad fact sheets that merely contain one common word (e.g. "sleep" in
        an unrelated guideline), the main source of off-topic answer drift.
        """
        if not groups:
            return 0.0
        text = " ".join([document.entity, *document.aliases, document.title, document.text])
        total = 2 * cls.subject_coverage(document, groups)
        for group in groups:
            matched = [term for term in group if cls.contains(text, [term])]
            if matched:
                total += 1.0
        return total

    @classmethod
    def tokens(cls, query):
        return set(tokenize(cls.GENERIC.sub(" ", query)))
