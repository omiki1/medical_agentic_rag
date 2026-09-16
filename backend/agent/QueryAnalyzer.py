import re

import agent.SafetyRouter as SafetyRouter
from agent.entity.AgentState import Analysis, Plan
from agent.QueryTopics import QueryTopics

FACET_WORDS = {
    "symptom": ["症状", "表现", "征兆", "口渴", "多尿", "咳嗽", "体重下降", "喘鸣"],
    "prevention": [
        "预防",
        "避免",
        "防治",
        "生活方式",
        "运动",
        "管理",
        "戒烟",
        "水果",
        "能吃",
        "可以吃",
        "吃什么",
        "吃饭",
        "食物",
        "注意",
    ],
    "medication": ["药", "二甲双胍", "胰岛素", "ACE", "ARB"],
    "test": ["检查", "检测", "筛查", "测量", "确诊", "诊断", "有没有", "怎么知道"],
    "treatment": ["治疗", "治愈", "怎么办"],
    "cause": ["病因", "原因", "引起", "导致", "传染", "传播", "感染", "遗传"],
    "department": ["科室", "挂什么科", "挂哪个科"],
    "diet": ["饮食", "吃什么食物", "吃什么好", "忌口", "不能吃什么", "宜吃什么"],
    "complication": ["并发症", "后果"],
    "association": ["关系", "关联", "联系"],
}
FACET_LABELS = {
    "overview": "概述",
    "symptom": "症状",
    "prevention": "预防与管理",
    "medication": "用药知识",
    "test": "检查",
    "treatment": "治疗原则",
    "cause": "病因与传播",
    "department": "就诊科室",
    "diet": "饮食",
    "complication": "并发症",
    "association": "关联",
}
FACET_RELATIONS = {
    "symptom": ["DISEASE_SYMPTOM"],
    "medication": ["DISEASE_DRUG"],
    "test": ["DISEASE_CHECK"],
    "department": ["DISEASE_DEPARTMENT"],
    "complication": ["DISEASE_ACOMPANY"],
    "treatment": ["DISEASE_CUREWAY"],
    "diet": ["DISEASE_DO_EAT", "DISEASE_NOT_EAT"],
}
EMERGENCY = [
    "胸痛",
    "胸口疼",
    "呼吸困难",
    "喘不过气",
    "喘不上气",
    "无法呼吸",
    "大出血",
    "意识丧失",
    "昏迷",
    "叫不醒",
    "失去意识",
    "不省人事",
    "突然偏瘫",
    "口角歪斜",
    "抽搐不止",
    "咯血不止",
    "呕血",
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "unconscious",
    "severe bleeding",
]
EXPANSIONS = {
    "老想喝水": "口渴",
    "总喝水": "口渴",
    "总想喝水": "口渴",
    "老是喝水": "口渴",
    "一直喝水": "口渴",
    "老上厕所": "多尿",
    "尿多": "多尿",
    "变瘦": "体重下降",
    "瘦了": "体重下降",
    "高压": "收缩压",
    "血糖病": "糖尿病",
    "消渴症": "糖尿病",
    "头疼": "头痛",
    "肚子疼": "腹痛",
    "肚子痛": "腹痛",
    "上吐下泻": "腹泻 呕吐",
    # 口语/方言 → 规范医学词（普通人不会说"腹泻"）
    "拉肚子": "腹泻",
    "拉稀": "腹泻",
    "窜稀": "腹泻",
    "闹肚子": "腹泻",
    "坏肚子": "腹泻",
    "吃坏东西": "食物中毒",
    "又拉又吐": "腹泻 呕吐",
    "又吐又拉": "呕吐 腹泻",
    "拉水": "腹泻 水样便",
    "拉肚子拉水": "腹泻 水样便",
    "脑壳疼": "头痛",
    "脑壳痛": "头痛",
    "脑袋疼": "头痛",
    "脑袋痛": "头痛",
    "头要炸了": "剧烈头痛",
    "太阳穴疼": "头痛",
    "太阳穴痛": "头痛",
    "一跳一跳的疼": "头痛",
    "晕乎乎": "头晕",
    "晕晕乎乎": "头晕",
    "昏昏沉沉": "头晕",
    "头重脚轻": "头晕",
    "浑身没劲": "乏力",
    "身上没劲": "乏力",
    "没力气": "乏力",
    "没精神": "乏力",
    "犯恶心": "恶心",
    "反胃": "恶心 呕吐",
    "想吐": "恶心 呕吐",
    "恶心反胃": "恶心 呕吐",
    "烧心": "反酸 烧心",
    "反酸水": "反酸",
    "胃胀": "腹胀",
    "肚子胀": "腹胀",
    "胀气": "腹胀",
    "翻江倒海": "恶心 胃部不适",
    "打嗝": "嗳气",
    "心慌慌": "心悸 心慌",
    "心里发慌": "心悸",
    "心发慌": "心悸",
    "出冷汗": "出冷汗 乏力",
    "难受死了": "不适",
    "好难受": "不适",
    # 情境化口语 → 规范医学词
    "眼前发黑": "眼前发黑 头晕",
    "站起来发黑": "体位性头晕",
    "站起来头晕": "体位性头晕",
    "一站起来": "体位性",
    "蹲下起来": "体位性头晕",
    "起猛了": "体位性头晕",
    "跑厕所": "腹泻 频繁如厕",
    "肚子咕咕叫": "腹泻 肠鸣",
    "拉个不停": "腹泻",
    "红疙瘩": "皮疹",
    "起疙瘩": "皮疹",
    "起红点": "皮疹",
    "一片一片的痒": "皮疹 瘙痒",
    "身上痒": "皮疹 瘙痒",
    "特别痒": "瘙痒",
    "一吃东西就难受": "进食后不适",
    "吃不下饭": "食欲不振",
    "睡不踏实": "失眠 睡眠质量差",
    "躺下就心慌": "心悸",
    "晚上心慌": "心悸 失眠",
    "喘不上来气": "呼吸困难",
    "上不来气": "呼吸困难",
}


def emergency_terms(question: str):
    result = []
    lowered = question.lower()
    academic = bool(re.search(r"科普|定义|教材|论文|什么是|急救知识|有哪些原因|的原因|的鉴别|机制", lowered))
    current = bool(re.search(r"我|现在|此刻|正在|家人|父亲|母亲|爸爸|妈妈|孩子|my |i am|i have", lowered))
    if academic and not current:
        return []
    terms = list(EMERGENCY)
    # Sudden severe headache and FAST-like descriptions, based on NHS headache/stroke guidance.
    # Match the current description, then apply the same local negation handling as fixed terms.
    if re.search(r"突然|突发|刚刚", lowered):
        terms += ["说话不清楚", "说话含糊", "说不出话", "一侧无力", "右边手脚没力气", "左边手脚没力气"]
        for clause in re.split(r"[，。；！？,;.!?]", lowered):
            if (
                re.search(r"突然|突发", clause)
                and re.search(r"头痛|头疼", clause)
                and re.search(r"剧烈|炸开|爆炸|最疼|最痛|从未.{0,4}疼|雷击", clause)
            ):
                if not re.search(r"没有|否认|并无|未出现", clause):
                    result.append("突发剧烈头痛")
    for term in terms:
        for match in re.finditer(re.escape(term), lowered):
            prefix = re.split(r"[，。；！？,;.!?]|但是|不过|但", lowered[: match.start()])[-1]
            if re.search(
                r"(?:没有|并无|否认|不伴|未出现|无|不再).{0,5}$|(?:no|without|not having)\s*$", prefix
            ):
                continue
            result.append(term)
    return sorted(set(result))


class QueryAnalyzer:
    def __init__(self, corpus):
        drugs = set(getattr(corpus, "drug_names", [])) | {"二甲双胍", "胰岛素", "布洛芬", "对乙酰氨基酚"}
        self.drug_pattern = re.compile(
            "|".join(re.escape(name) for name in sorted(drugs, key=lambda x: (-len(x), x)))
        )
        aliases = dict(corpus.aliases)
        for names in QueryTopics.NAMED_SYNONYMS:
            canonical = next((aliases[name] for name in names if name in aliases), None)
            if canonical:
                for name in names:
                    aliases.setdefault(name, canonical)
        self.aliases = sorted(aliases.items(), key=lambda x: (-len(x[0]), x[0]))

    def analyze(self, question, previous_question=""):
        # Check the CURRENT utterance before normalization or history use.
        emergencies = emergency_terms(question)
        risk = SafetyRouter.classify(question)
        query = question.strip()
        for source, target in EXPANSIONS.items():
            query = query.replace(source, target)
        entities = self.extract(query)
        contextualized = False
        # 这句问句是否自带主语（症状或人群）。
        # 自带主语的问句是完整问题，既不该继承上一轮的实体，也不该被当成"信息不全"而要求补充。
        # 线上真实故障："3岁小孩发烧怎么办" 没有疾病实体，被 followup 的兜底分支命中，
        # 于是走"追问但无实体无上文"这条路，回了"请补充你想了解的疾病或症状…"，
        # 把一个能答的常见问题堵死了。
        own_subject = bool(
            re.search(
                r"孩子|儿童|婴儿|老人|孕妇|孕期|哺乳|发烧|发热|咳嗽|头痛|头疼|头晕|眩晕|"
                r"腹泻|拉肚子|呕吐|恶心|肚子疼|腹痛|失眠|便秘|皮疹|乏力|心悸|心慌|血压|血糖",
                query,
            )
        )
        # 年龄与人群背景。用户已经给出这些信息时，再要求他"补充年龄/人群"就是答非所问：
        # 线上真实故障——问"3岁小孩发烧怎么办，头痛，浑身不舒服"，系统回"请先补充…年龄…"。
        # 注意这里**只**含年龄与人群，不含症状：单独的"肚子疼怎么办"仍应询问更多背景
        # （见 test_short_personal_symptom_requests_ask_context_without_assigning_a_child）。
        has_population = bool(
            re.search(
                r"\d+\s*(?:岁|周岁|个月|月龄)|新生儿|婴幼儿|青少年|成人|老年|"
                r"孩子|儿童|婴儿|老人|孕妇|孕期|哺乳",
                query,
            )
        )
        # Follow-up detection: explicit linking words, confirmation/continuation
        # particles ("是的/对/好/嗯…"), or a short intent-only utterance that has no
        # subject of its own ("应该去看医生吗", "需要吃药吗"). In all these cases the
        # previous turn's entities (from L3 episode memory) supply the missing subject,
        # so a reply like "是的，我应该怎么办" after "上吐下泻" is not re-asked.
        followup = bool(
            re.match(
                r"^(那|那么|它|这种病|这个病|还|又|具体|有哪些|怎么|如何|需要|能否|"
                r"是(的|呀|吗)?[,，]?|对(的|呀|,|，|！|!)?|嗯|好(的|呀|吧)?[,，]?|"
                r"恩|然后|之后|接着|之后呢|然后呢|"
                r"(?:应该|需要|可以|要|得|该)[^，。]{0,12}?(?:怎么办|看医生|吃药|注意|检查|治疗|忌口)?|"
                r"[^，。]{0,8}?(?:怎么办|该注意什么|要不要紧|严重吗))",
                query,
            )
        )
        if not entities and previous_question and followup:
            # A fresh utterance that names its own symptom/population is a NEW question,
            # not a follow-up to the previous entities (e.g. "孩子发烧怎么办" after a
            # 腹泻 turn must not inherit 腹泻).
            if not own_subject:
                previous = self.extract(previous_question)
                if previous:
                    entities = previous
                    query = "、".join(previous) + " " + query
                    contextualized = True
        facets = [
            facet for facet, words in FACET_WORDS.items() if any(w.lower() in query.lower() for w in words)
        ]
        facets = facets or ["overview"]
        named_drug = bool(self.drug_pattern.search(query))
        if named_drug and facets == ["overview"]:
            facets = ["medication"]
        if re.search(r"是什么|什么是|定义|概念", query) and not re.search(r"原因|引起|导致", query):
            facets = ["overview"]
        elif entities and re.search(r"会不会是|是不是得了|是不是患了", query):
            facets = ["symptom"]
        groups = QueryTopics.groups(query, entities)
        nonmedical = bool(
            re.search(r"天气|动漫|写代码|写诗|炒股|比特币|足球|随机角色|python代码|python爬虫", query.lower())
        )
        medicine = named_drug or bool(re.search(r"药|剂量|毫克|mg|几片|服用|片|胶囊", query, re.I))
        personal = bool(
            re.search(
                r"剂量|多少毫克|多少mg|几片|换药|停药|开处方|开药|开个|给(?:我|他|她|我妈|我爸)?开|处方|首选|禁忌|相互作用|"
                r"不用吃|不吃了|减半|减量|减一半|一半量|半量|加量|加半|继续吃|继续服|停一下|停掉|停用|还吃|还服|"
                r"自己停|自行停|自己减|自行减|把药停|把药减|药停|药减|"
                r"吃一片行不行|吃半片|明天.{0,4}吃|今天.{0,4}吃|多久能停|能不能停",
                query,
                re.I,
            )
        )
        if medicine and re.search(r"吃多少|能吃吗|能不能吃|安全吗|能.{0,3}吃|可以.{0,3}吃|该吃|要吃", query):
            personal = True
        if (
            medicine
            and re.search(r"我|孩子|孕妇|孕期|哺乳", query)
            and re.search(r"用什么药|吃什么药|服用|可以吃|该吃", query)
        ):
            personal = True
        if (
            medicine
            and re.search(r"孕妇|孕期|怀孕|哺乳|儿童|孩子", query)
            and re.search(r"用|吃|服|适合", query)
        ):
            personal = True
        constraints = [
            word
            for word in ["孕妇", "孕期", "儿童", "哺乳", "肾功能不全", "肝功能不全", "1型", "一型"]
            if word in query
        ]
        if "怀孕" in query:
            constraints.append("孕期")
        if "最新" in query or "今年" in query:
            constraints.append("最新资料")
        symptom_request = bool(re.search(r"腹痛|头痛|发热|咳嗽|眩晕|胸闷", query) and "怎么办" in query)
        clarification = ""
        has_timing = bool(
            re.search(r"\d+\s*(?:天|月|年|周|小时|分钟)|昨天|今天|昨晚|最近|多年|长期|突然", query)
        )
        general_advice = bool(re.search(r"一般|通常|科普|资料|常见", query))
        # 只有"给了症状但没给任何人群/年龄背景"时才追问。
        # 一旦用户说了"3岁/小孩/孕妇/老人"，就已经具备回答一般性处理建议的条件；
        # 此时索要"年龄"既多余又会让用户觉得系统没读他的话。
        if symptom_request and not has_timing and not general_advice and not has_population:
            clarification = "请先补充：症状的具体部位、持续多久、严重程度，以及是否伴有发热、呕吐或其他不适。年龄和是否怀孕也会影响下一步判断。仅凭这一句话无法判断病因。"
        # Vague, purely emotional complaints ("难受死了" "浑身不舒服") without any concrete
        # symptom or body part should be asked to be specific, not answered with random
        # retrieved pages (off-topic) nor rejected coldly.
        concrete_mention = bool(
            re.search(
                r"头|脑|眼|耳|鼻|喉|嗓|牙|胸|心|胃|腹|肚|腰|背|腿|膝|关节|皮肤|手脚|拉|吐|泻|稀|烧|咳|"
                r"疼|痛|晕|麻|肿|胀|酸|汗|渴|饿|睡|梦",
                query,
            )
            and not re.search(r"哪(?:里|儿)?(?:疼|痛|不舒服|难受)|说不上|说不清|也说不清|不知道哪", query)
        )
        vague_feel = bool(
            re.search(
                r"难受|不舒服|不适|没劲|不行了|浑身|全身|整个人都不好|不得劲|说不清|说不上",
                query,
            )
        )
        if not entities and not concrete_mention and vague_feel:
            clarification = "请具体描述哪里不舒服：是哪个部位（头/胸/腹/关节等），持续多久，什么感觉（疼/胀/晕/乏力等），有没有发烧、呕吐等伴随表现。仅凭感受很难判断原因。"
        # 只给了人群/年龄，但完全没说哪里不舒服（"3岁小孩怎么办"）。
        # 这类问句既没有可检索的症状，也没有疾病实体，必须先问清症状；
        # 否则模型只能凭年龄泛泛而谈，等于答非所问。
        #
        # 判据刻意**不**依赖症状关键词枚举：靠枚举必然会漏（"感冒"就曾漏掉，
        # 导致"孕妇感冒了怎么办"被误判成"只有人群没有症状"）。
        # 改为判断：去掉人群/年龄词与问句套话之后，是否还剩实质内容。
        population_stripped = re.sub(
            r"\d+\s*(?:岁|周岁|个月|月龄)|新生儿|婴幼儿|青少年|成人|老年|"
            r"孩子|儿童|婴儿|小儿|小孩|宝宝|老人|孕妇|孕期|怀孕|哺乳|的|了|呢|啊|吗|呀|",
            "",
            query,
        )
        population_stripped = re.sub(r"怎么办|怎么处理|如何处理|如何|怎么|办|处理|应该|需要|要|请问|一下", "", population_stripped)
        if not entities and has_population and not clarification and len(population_stripped) == 0:
            clarification = (
                "请补充孩子具体哪里不舒服：有哪些症状（发热、咳嗽、呕吐、腹泻、皮疹等）、"
                "持续多久、精神状态和进食饮水情况。有了具体症状才能给出对应的资料与处理建议。"
                if re.search(r"孩子|儿童|婴儿|小儿|个月|岁|新生儿|婴幼儿", query)
                else "请补充具体有哪些症状、持续多久、严重程度，以及有没有其他伴随表现；"
                "有了具体症状才能给出对应的资料与处理建议。"
            )
        if not entities and any(x in query for x in ["口渴", "多尿", "体重下降", "咳嗽", "发热"]):
            # Symptom descriptions can retrieve information, never establish etiology.
            facets = ["symptom"]
        return Analysis(
            original=question,
            query=query,
            entities=entities,
            topic_groups=groups,
            symptom_request=symptom_request,
            clarification_prompt=clarification,
            facets=facets,
            intent=facets[0],
            emergency=(risk.level == SafetyRouter.EMERGENCY)
            or (
                bool(emergencies)
                and risk.level == SafetyRouter.NONE
                and risk.code not in {"historical_context", "academic_context", "hypothetical_context"}
            ),
            emergency_terms=emergencies or ([risk.code] if risk.code else []),
            risk_level=risk.level,
            risk_code=risk.code,
            risk_band_message=risk.band_message,
            out_of_scope=nonmedical,
            fabrication_request=bool(
                re.search(
                    r"(?:编造|伪造|捏造|编\d*篇|编几篇|写\d*篇|写几篇|造一个|瞎编|胡编|帮我编|给我编|帮我写|给我写)"
                    r".{0,15}(?:论文|证据|研究结果|病例|文献|引用|来源)",
                    query,
                )
            )
            and not bool(re.search(r"识别|辨别|防止|如何发现|帮我查|帮我找|总结|参考", query)),
            personal_treatment=personal,
            # 追问信号只在"问句自己没有主语"时才算信息不足。自带症状/人群的问句
            # （如"3岁小孩发烧怎么办"）是完整问题，不该被要求补充背景。
            needs_clarification=bool(clarification)
            or (not entities and followup and not own_subject and not contextualized)
            or not groups,
            contextualized=contextualized,
            wants_latest="最新资料" in constraints,
            constraints=constraints,
        )

    def extract(self, query):
        lowered = query.lower()
        occupied = set()
        matches = []
        for alias, entity in self.aliases:
            pattern = r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])" if alias.isascii() else re.escape(alias)
            for match in re.finditer(pattern, lowered):
                span = set(range(match.start(), match.end()))
                if span & occupied:
                    continue
                occupied.update(span)
                if entity not in matches:
                    matches.append(entity)
        return matches[:6]


def make_plan(analysis, settings, dense_available):
    graph = bool(analysis.entities) and any(f in FACET_RELATIONS for f in analysis.facets)
    hyde = not analysis.entities and dense_available and settings.provider == "compatible"
    routes = (["dense", "bm25"] if dense_available else ["bm25"]) + (["graph"] if graph else [])
    if hyde:
        routes.append("hyde")
    pubmed = analysis.wants_latest and settings.pubmed_enabled
    if pubmed:
        routes.append("pubmed")
    reason = "精确词与语义互补召回" if dense_available else "使用可用的关键词索引召回"
    if graph:
        reason += "；命中实体与关系意图，补充有来源的图谱路径"
    return Plan(routes=routes, use_graph=graph, use_hyde=hyde, use_pubmed=pubmed, reason=reason)
