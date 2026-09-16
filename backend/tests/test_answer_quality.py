import asyncio
from datetime import date
from types import SimpleNamespace

from agent.AnswerGrader import AnswerGrader
from agent.entity.AgentState import Draft
from agent.EvidenceGrader import EvidenceGrader
from agent.GroundedAnswerService import GroundedAnswerService
from agent.MedicalAgent import excerpt
from agent.QueryAnalyzer import QueryAnalyzer
from common.TranslationService import TranslationService, clean_title, is_english
from rag.entity.Evidence import Document, Evidence

from tests.test_contracts import Fixtures


class AnswerQualityContracts(Fixtures):
    def test_drug_name_without_the_word_medicine_and_unresponsive_patient(self):
        analyzer = QueryAnalyzer(self.corpus)
        self.assertTrue(analyzer.analyze("我怀孕了，能自己吃布洛芬吗").personal_treatment)
        self.assertTrue(analyzer.analyze("孩子叫不醒了怎么办").emergency)
        self.assertTrue(analyzer.analyze("编造三篇论文证明某药有效").fabrication_request)
        self.assertFalse(analyzer.analyze("如何辨别伪造医学论文").fabrication_request)

    def test_english_dengue_matches_the_chinese_disease_name(self):
        from agent.EvidencePolicy import EvidencePolicy
        from agent.QueryTopics import QueryTopics

        doc = Document(
            id="dengue",
            source_id="who",
            entity="Dengue",
            facet="symptom",
            title="Dengue",
            text="Dengue can cause fever and a severe headache.",
            source_title="WHO",
        )
        analysis = QueryAnalyzer(self.corpus).analyze("登革热有哪些症状")
        self.assertTrue(EvidencePolicy.entity_matches(doc, "登革热"))
        self.assertEqual(QueryTopics.coverage(doc, analysis.topic_groups), 1)

    def test_answers_have_no_mode_preface_and_one_final_disclaimer(self):
        from agent.MedicalAgent import DISCLAIMER, MedicalAgent

        agent = MedicalAgent(self.corpus, self.retriever, self.settings)
        for mode, query in [
            ("exploratory", "高血压有哪些症状"),
            ("authoritative", "肚子疼怎么办"),
            ("exploratory", "我胸痛喘不过气"),
        ]:
            result = asyncio.run(agent.run(query, mode=mode))
            self.assertFalse(result.answer.startswith("探索模式"))
            self.assertEqual(result.answer.count(DISCLAIMER), 1)
            self.assertTrue(result.answer.endswith(DISCLAIMER))

    def test_legacy_screening_frequency_is_not_used_as_answer_support(self):
        doc = Document(
            id="bone",
            source_id="old",
            entity="骨质疏松",
            facet="prevention",
            title="骨质疏松",
            text="均衡饮食和适当运动有助于维护骨骼健康。建议每年进行一次骨密度检查。绝经后应长期雌激素替代治疗。",
            source_title="测试",
        )
        passages = GroundedAnswerService.passages([Evidence(document=doc)])
        self.assertTrue(passages)
        self.assertTrue(
            all("骨密度检查" not in p["text"] and "激素替代" not in p["text"] for p in passages.values())
        )

    def test_complementary_chunks_from_one_source_are_not_dropped(self):
        analysis = QueryAnalyzer(self.corpus).analyze("血压高到多少算高血压")
        common = dict(
            source_id="same-who-page",
            entity="高血压",
            facet="overview",
            title="高血压",
            source_title="测试",
            review_status="source_checked",
        )
        brief = Document(id="brief", text="高血压需要通过规范测量进行判断。", **common)
        detail = Document(
            id="detail", text="在两个不同日子测量，收缩压至少140毫米汞柱和/或舒张压至少90毫米汞柱。", **common
        )
        selected = GroundedAnswerService.select_evidence(
            [Evidence(document=brief, relevance=0.9), Evidence(document=detail, relevance=0.8)], analysis
        )
        self.assertEqual({ev.document.id for ev in selected}, {"brief", "detail"})

    def test_added_sources_do_not_alias_food_or_symptoms_to_diagnoses(self):
        import json
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "data" / "quality_support.jsonl"
        forbidden = {"水果", "血糖", "血压", "胃胀", "打嗝", "减盐"}
        for line in source.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            self.assertFalse(forbidden.intersection(row["aliases"]), row["id"])

    def test_ambiguous_salt_units_are_not_sent_as_support(self):
        doc = Document(
            id="salt",
            source_id="who",
            title="高血压",
            text="不要吃含盐太多的食物（尽量保持每天在2克以下）。通过运动和戒烟也有助于预防高血压。",
            source_title="测试",
        )
        passages = GroundedAnswerService.passages([Evidence(document=doc)])
        self.assertTrue(passages)
        self.assertFalse(any("2克" in p["text"] for p in passages.values()))

    def test_obvious_legacy_misinformation_is_never_eligible(self):
        analysis = QueryAnalyzer(self.corpus).analyze("高血压怎么预防")
        analysis.mode = "exploratory"
        doc = Document(
            id="bad-cure",
            source_id="bad",
            entity="高血压",
            facet="prevention",
            title="高血压",
            text="癌症不能在弱碱性的人体中形成。转变为弱碱性就会治好。",
            source_title="测试",
        )
        grade = EvidenceGrader().grade(analysis, [Evidence(document=doc, relevance=0.99)])
        self.assertFalse(grade.eligible_ids)

    def test_failed_generation_cannot_bypass_review_by_returning_excerpts(self):
        from unittest.mock import AsyncMock

        from agent.MedicalAgent import MedicalAgent

        settings = self.settings.model_copy(update={"provider": "compatible"})
        agent = MedicalAgent(self.corpus, self.retriever, settings)
        agent.answers.generate = AsyncMock(return_value=(None, None, [{"stage": "semantic_review"}]))
        result = asyncio.run(agent.run("高血压有哪些症状", fixed=True))
        self.assertEqual(result.status, "abstained")
        self.assertEqual(result.generation_mode, "generation_unavailable")
        self.assertNotIn("[E", result.answer)

    def test_colloquial_red_flags_negation_and_food_vs_drug_dosing(self):
        analyzer = QueryAnalyzer(self.corpus)
        # 卒中组合是立即急救；突发剧烈头痛按风险分级为"尽快就医"(urgent)，不再是 emergency。
        self.assertTrue(analyzer.analyze("我爸爸突然说话不清楚，右边手脚没力气").emergency)
        sudden = analyzer.analyze("我突然头痛得像炸开一样")
        self.assertFalse(sudden.emergency)
        self.assertEqual(sudden.risk_level, "urgent")
        for question in [
            "没有胸痛，也没有呼吸困难，最近睡不好",
            "没有突然剧烈头痛",
            "科普：突然剧烈头痛有哪些原因",
        ]:
            self.assertFalse(analyzer.analyze(question).emergency, question)
        self.assertTrue(analyzer.analyze("我吃的二甲双胍每天可以加到几片").personal_treatment)
        self.assertFalse(analyzer.analyze("我有糖尿病可以吃水果吗").personal_treatment)

    def test_pubmed_research_allowed_for_latest_in_authoritative(self):
        # PubMed 文献在"最新/今年"的权威模式下可作为补充证据进入 eligible，
        # 但个人换药/用药仍被拒绝；普通（非 latest）权威问题文献不放行。
        from datetime import date

        from agent.AnswerGrader import AnswerGrader
        from agent.EvidenceGrader import EvidenceGrader
        from agent.QueryAnalyzer import QueryAnalyzer
        from agent.entity.AgentState import Claim, Draft
        from rag.entity.Evidence import Document, Evidence

        doc = Document(
            id="pubmed:1", source_id="pubmed:1", entity="高血压", title="Novel therapy for hypertension 2025",
            text="A 2025 randomized trial found a new approach to hypertension treatment improved control.",
            source_title="PubMed · 待专业解读的文献摘要",
            source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
            source_type="research", language="en",
        )
        lit = Evidence(document=doc, methods=["pubmed"], relevance=0.6)

        latest = QueryAnalyzer(self.corpus).analyze("高血压 今年 有什么新的治疗方法")
        latest.mode = "authoritative"
        grade = EvidenceGrader().grade(latest, [lit])
        self.assertIn("pubmed:1", grade.eligible_ids)
        self.assertTrue(grade.sufficient)

        # 非 latest 的权威问题不放行 research（普通查询仍需核验来源）
        normal = QueryAnalyzer(self.corpus).analyze("高血压怎么治疗")
        normal.mode = "authoritative"
        grade2 = EvidenceGrader().grade(normal, [lit])
        self.assertNotIn("pubmed:1", grade2.eligible_ids)

        # 个人换药（latest 也不行）：文献不能替代医生
        personal = QueryAnalyzer(self.corpus).analyze("我高血压想换药，最新指南怎么说")
        personal.mode = "authoritative"
        grade3 = EvidenceGrader().grade(personal, [lit])
        self.assertFalse(grade3.sufficient)

    def test_theme_ties_keep_stronger_evidence_first_and_relabel_citations(self):
        from rag.service.RAGService import RAGService

        analysis = QueryAnalyzer(self.corpus).analyze("高血压有哪些症状")
        document = next(d for d in self.corpus.reviewed if d.entity == "高血压" and d.facet == "symptom")
        weak = Evidence(
            document=document.model_copy(update={"id": "weak"}), relevance=0.51, citation_id="E1", rank=1
        )
        strong = Evidence(
            document=document.model_copy(update={"id": "strong"}), relevance=0.95, citation_id="E2", rank=2
        )
        evidence = [weak, strong]
        RAGService.order_evidence(evidence, analysis)
        self.assertEqual(evidence[0].document.id, "strong")
        self.assertEqual([(ev.rank, ev.citation_id) for ev in evidence], [(1, "E1"), (2, "E2")])

    def test_medical_topics_are_not_out_of_scope_or_an_inferred_diagnosis(self):
        analyzer = QueryAnalyzer(self.corpus)
        for question in ["血糖和血压有关系吗", "睡眠问题可能是什么原因导致的", "头疼可能是什么导致的"]:
            analysis = analyzer.analyze(question)
            self.assertFalse(analysis.out_of_scope)
            self.assertTrue(analysis.topic_groups)
        analysis = analyzer.analyze("血糖和血压有关系吗")
        self.assertNotIn("糖尿病", analysis.entities)
        self.assertNotIn("高血压", analysis.entities)

    def test_sleep_question_rejects_high_scoring_infertility_text_in_both_modes(self):
        document = Document(
            id="unrelated",
            source_id="who-test",
            entity="不孕症",
            facet="cause",
            title="不孕症的病因",
            text="不孕症可能由男性或女性生殖系统的许多因素引起。",
            source_title="测试来源",
            review_status="source_checked",
            published_at=date.today(),
            checked_at=date.today(),
        )
        analysis = QueryAnalyzer(self.corpus).analyze("睡眠问题可能是什么原因导致的")
        for mode in ["authoritative", "exploratory"]:
            analysis.mode = mode
            grade = EvidenceGrader().grade(analysis, [Evidence(document=document, relevance=0.99)])
            self.assertFalse(grade.sufficient)
            self.assertFalse(grade.eligible_ids)

    def test_public_host_discovery_is_safe_and_opt_in(self):
        """公网 IP 自动发现：可关闭、拿不到时安静跳过、绝不把 HTML 当主机名。

        背景：按量付费 ECS 的"普通公网 IP"在停止/启动后会被重新分配，
        而 MED_ALLOWED_ORIGINS 写死旧地址 → 重启后访问得到一个没有说明的 400，
        看起来像"服务挂了"。所以启动时向元数据服务查一次当前公网 IP。
        线上实测：eipv4 返回真 IP，而 public-ipv4 返回 404 HTML 页面，
        因此格式校验是必需的 —— 否则整段 HTML 会被塞进主机白名单。
        """
        from unittest.mock import patch

        from Application import MedicalApplication

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def read(self, _n=None):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        # 关闭时完全不联网
        off = self.settings.model_copy(update={"discover_public_host": False})
        self.assertEqual(MedicalApplication.discovered_hosts(off), set())

        on = self.settings.model_copy(update={"discover_public_host": True})

        # 元数据服务不可达 → 安静返回空集合，不能抛异常影响启动
        with patch("urllib.request.urlopen", side_effect=OSError("unreachable")):
            self.assertEqual(MedicalApplication.discovered_hosts(on), set())

        # 返回 HTML 404 页面时不能被当成主机名
        html = b'<?xml version="1.0"?><html>404 Not Found</html>'
        with patch("urllib.request.urlopen", return_value=FakeResponse(html)):
            self.assertEqual(MedicalApplication.discovered_hosts(on), set())

        # 合法 IP 才会被采纳
        with patch("urllib.request.urlopen", return_value=FakeResponse(b"47.242.164.211")):
            self.assertEqual(MedicalApplication.discovered_hosts(on), {"47.242.164.211"})

    def test_short_personal_symptom_requests_ask_context_without_assigning_a_child(self):
        analysis = QueryAnalyzer(self.corpus).analyze("肚子疼怎么办")
        self.assertTrue(analysis.needs_clarification)
        self.assertIn("持续多久", analysis.clarification_prompt)
        self.assertNotIn("孩子", analysis.clarification_prompt)

    def test_question_with_its_own_subject_is_not_treated_as_missing_context(self):
        """自带症状或人群的问句是完整问题，不该被要求补充背景。

        线上真实故障：问"3岁小孩发烧怎么办"，系统回
        "请补充你想了解的疾病或症状，以及需要了解的是症状、检查还是预防。"
        原因是 followup 的正则有个兜底分支 `[^，。]{0,8}?(?:怎么办|…)`，
        几乎任何以"怎么办"结尾的短问句都会被判成"追问"；而"追问 + 无疾病实体 + 无上文"
        就强制要求澄清，且 clarification_prompt 为空 → 兜底成那句泛泛的提示。
        结果是一个能正常回答的常见问题被堵死。
        """
        for query in [
            "3岁小孩发烧怎么办",
            "小孩发烧怎么处理",
            "孩子发烧怎么办",
            "发烧怎么办",
            "孕妇感冒了怎么办",
            "老人头晕怎么办",
        ]:
            analysis = QueryAnalyzer(self.corpus).analyze(query)
            self.assertFalse(analysis.needs_clarification, query)
            self.assertEqual(analysis.clarification_prompt, "", query)

    def test_still_asks_for_context_when_there_is_no_subject_at_all(self):
        """没有症状也没有人群时才该追问 —— 修复不能把该拦的也放过去。"""
        for query in ["我难受死了怎么办", "浑身不舒服怎么办"]:
            analysis = QueryAnalyzer(self.corpus).analyze(query)
            self.assertTrue(analysis.needs_clarification, query)
            self.assertTrue(analysis.clarification_prompt, query)

    def test_given_age_is_not_asked_for_again(self):
        """用户已经说了年龄，就不能再要求他补充年龄。

        线上真实故障：问"3岁小孩发烧怎么办，头痛，浑身不舒服"，
        系统回"请先补充：症状的具体部位、持续多久…年龄和是否怀孕也会影响下一步判断"。
        用户已经说了"3岁"，这是答非所问。
        """
        analysis = QueryAnalyzer(self.corpus).analyze("3岁小孩发烧怎么办，头痛，浑身不舒服")
        self.assertFalse(analysis.needs_clarification)
        self.assertNotIn("年龄", analysis.clarification_prompt)

        # 各种年龄/人群写法都应被认出
        for query in [
            "5个月婴儿咳嗽怎么办",
            "10岁儿童头痛怎么办",
            "孕妇发烧怎么办",
            "老人腹泻怎么办",
        ]:
            a = QueryAnalyzer(self.corpus).analyze(query)
            self.assertFalse(a.needs_clarification, query)

    def test_age_alone_still_asks_for_missing_symptom_detail(self):
        """只有年龄、没有任何症状时，仍应追问具体症状。"""
        analysis = QueryAnalyzer(self.corpus).analyze("3岁小孩怎么办")
        self.assertTrue(analysis.needs_clarification)
        self.assertTrue(analysis.clarification_prompt)

    def test_paraphrase_needs_semantic_review_and_preserves_source_support(self):
        analysis = QueryAnalyzer(self.corpus).analyze("高血压有哪些症状")
        document = next(d for d in self.corpus.reviewed if d.entity == "高血压" and d.facet == "symptom")
        evidence = [Evidence(document=document, relevance=0.95)]
        raw = {
            "claims": [
                {
                    "text": "高血压不一定有明显症状，因此不能仅凭自我感觉判断。",
                    "evidence_ids": [document.id],
                    "quotes": [document.text],
                }
            ]
        }
        pending = AnswerGrader().grade(Draft.model_validate(raw), evidence, analysis, synthesized=True)
        self.assertFalse(pending.passed)
        self.assertEqual(pending.verification, "semantic_review_pending")

        class Generator:
            async def json(self, instruction, payload, budget):
                budget["calls"] += 1
                return {
                    "claims": [
                        {
                            "text": raw["claims"][0]["text"],
                            "support_ids": [p["id"] for p in payload["passages"]],
                        }
                    ]
                }

        class Reviewer:
            async def json(self, instruction, payload, budget):
                budget["calls"] += 1
                return {
                    "addresses_question": True,
                    "supported_claims": [0],
                    "unsafe_generalization": False,
                    "feedback": [],
                }

        async def scenario():
            settings = SimpleNamespace(max_model_calls=6)
            result, grade, _ = await GroundedAnswerService(Generator(), Reviewer(), settings).generate(
                evidence, analysis, {"calls": 0}
            )
            self.assertEqual(result.claims[0].text, raw["claims"][0]["text"])
            self.assertTrue(grade.passed)

            class RejectingReviewer(Reviewer):
                async def json(self, instruction, payload, budget):
                    budget["calls"] += 1
                    return {
                        "addresses_question": False,
                        "supported_claims": [],
                        "unsafe_generalization": False,
                        "feedback": ["没有回答问题"],
                    }

            budget = {"calls": 0}
            result, grade, attempts = await GroundedAnswerService(
                Generator(), RejectingReviewer(), settings
            ).generate(evidence, analysis, budget)
            self.assertIsNone(result)
            self.assertIsNone(grade)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(budget["calls"], 4)

        asyncio.run(scenario())

    def test_disabled_qa_is_not_opened_even_when_an_active_pointer_exists(self):
        from rag.retriever.QARetriever import QARetriever

        retriever = QARetriever(self.settings.model_copy(update={"qa_enabled": False}))
        self.assertIsNone(retriever.path)
        self.assertEqual(retriever.search("高血压"), [])

    def test_general_symptom_query_does_not_assume_child_or_pregnancy(self):
        from agent.EvidencePolicy import EvidencePolicy

        analysis = QueryAnalyzer(self.corpus).analyze("头疼可能是什么原因")
        for entity in ["小儿偏头痛", "妊娠合并偏头痛"]:
            doc = Document(
                id=entity,
                source_id=entity,
                title=entity,
                entity=entity,
                text="头痛的病因资料。",
                source_title="测试",
            )
            self.assertFalse(EvidencePolicy.population_matches(doc, analysis))

    def test_unrelated_disease_symptom_section_is_not_evidence_for_a_general_symptom_query(self):
        """泛化症状问题不得引用无关病种的"症状"章节。

        线上实测："小孩发烧38.5度怎么处理"引用了 B组链球菌/日本脑炎/呼吸道合胞病毒的
        symptom 章节 —— 只因这些页面症状列表里出现"发热"。单病种症状页不是泛化症状问题的证据。
        """
        from agent.EvidencePolicy import EvidencePolicy

        analysis = QueryAnalyzer(self.corpus).analyze("小孩发烧38.5度怎么处理")
        unrelated = Document(
            id="who:respiratory-syncytial-virus-(rsv):symptom:4:0",
            source_id="who:rsv",
            entity="呼吸道合胞病毒",
            facet="symptom",
            title="Respiratory syncytial virus — Symptoms",
            text="发热是常见症状。",
            source_title="WHO 事实清单 · 呼吸道合胞病毒",
            source_type="public_health",
        )
        self.assertTrue(EvidencePolicy.disease_specific_symptom_mismatch(unrelated, analysis))

    def test_symptom_section_survives_when_question_raises_that_disease(self):
        from agent.EvidencePolicy import EvidencePolicy

        named = QueryAnalyzer(self.corpus).analyze("登革热有哪些症状")
        dengue = Document(
            id="who:dengue:symptom:0:0",
            source_id="who:dengue",
            entity="登革热",
            facet="symptom",
            title="Dengue — Symptoms",
            text="登革热可引起发热和剧烈头痛。",
            source_title="WHO 事实清单 · 登革热",
            source_type="public_health",
        )
        self.assertFalse(EvidencePolicy.disease_specific_symptom_mismatch(dengue, named))

    def test_symptom_section_survives_when_the_document_entity_is_the_asked_symptom(self):
        """回归保护：曾修好"拉肚子怎么办"弃答，不能因本次过滤而复发。

        文档实体自身是症状（腹泻）时必须保留，而不是当成"无关病种症状页"排除。
        """
        from agent.EvidencePolicy import EvidencePolicy

        analysis = QueryAnalyzer(self.corpus).analyze("拉肚子怎么办")
        diarrhoea = Document(
            id="who:diarrhoeal-disease:symptom:0:0",
            source_id="who:diarrhoeal-disease",
            entity="腹泻",
            facet="symptom",
            title="Diarrhoeal disease — Symptoms",
            text="腹泻是主要表现。",
            source_title="WHO 事实清单 · 腹泻病",
            source_type="public_health",
        )
        self.assertFalse(EvidencePolicy.disease_specific_symptom_mismatch(diarrhoea, analysis))

    def test_exploratory_mode_keeps_the_wider_symptom_net(self):
        from agent.EvidencePolicy import EvidencePolicy

        analysis = QueryAnalyzer(self.corpus).analyze("小孩发烧38.5度怎么处理").model_copy(
            update={"mode": "exploratory"}
        )
        doc = Document(
            id="who:respiratory-syncytial-virus-(rsv):symptom:4:0",
            source_id="who:rsv",
            entity="呼吸道合胞病毒",
            facet="symptom",
            title="Respiratory syncytial virus — Symptoms",
            text="发热是常见症状。",
            source_title="WHO",
            source_type="public_health",
        )
        self.assertFalse(EvidencePolicy.disease_specific_symptom_mismatch(doc, analysis))

    def test_non_symptom_facets_are_unaffected_by_the_symptom_filter(self):
        from agent.EvidencePolicy import EvidencePolicy

        analysis = QueryAnalyzer(self.corpus).analyze("小孩发烧38.5度怎么处理")
        for facet in ["overview", "prevention", "treatment", "cause"]:
            doc = Document(
                id="who:rsv:" + facet,
                source_id="who:rsv",
                entity="呼吸道合胞病毒",
                facet=facet,
                title="RSV",
                text="资料。",
                source_title="WHO",
                source_type="public_health",
            )
            self.assertFalse(EvidencePolicy.disease_specific_symptom_mismatch(doc, analysis))

    @staticmethod
    def _fake_retriever(document_count, *, dense=True):
        """构造一个只用于检验"是否该拦探索模式"的伪检索器。

        exploration_blocked_reason 必须放在**类属性**上：这样才走描述符协议、
        调用时自动绑定实例；写成实例属性会变成普通函数、少一个 self 参数。
        """
        from rag.retriever.HybridRetriever import HybridRetriever

        class Corpus:
            documents = {str(i): object() for i in range(document_count)}

        class Retriever:
            corpus = Corpus()
            EXPLORATION_PREBUILD_THRESHOLD = 3000
            _exploration_ready = False
            _embedding = object()
            dense = None
            exploration_blocked_reason = HybridRetriever.exploration_blocked_reason

        retriever = Retriever()
        retriever.dense = object() if dense else None
        return retriever

    def test_exploration_mode_is_blocked_before_it_can_burn_a_core_for_an_hour(self):
        """探索模式缺索引时必须快速失败。

        线上真实故障：一次探索模式提问触发了 111,385 篇语料的全量向量编码，
        撞满 240 秒请求超时；而 asyncio.to_thread 起的编码线程无法取消，
        继续占满一个 CPU 核（实测已烧 396 秒且仍在跑），只能靠重启容器终止。
        """
        from chat.service.ChatService import ChatService

        retriever = self._fake_retriever(50_000)
        reason = ChatService.exploration_unavailable(SimpleNamespace(rag=SimpleNamespace(retriever=retriever)))
        self.assertIsInstance(reason, str)
        self.assertIn("尚未构建", reason)
        self.assertIn("60-90", reason)

        # 索引就绪后必须放行
        retriever._exploration_ready = True
        self.assertIsNone(
            ChatService.exploration_unavailable(SimpleNamespace(rag=SimpleNamespace(retriever=retriever)))
        )

    def test_small_corpus_and_missing_dense_never_block_exploration(self):
        """小语料按需构建很快；未配置嵌入模型时根本不会编码 —— 都不该被拦。"""
        from chat.service.ChatService import ChatService

        small = self._fake_retriever(50)
        self.assertIsNone(
            ChatService.exploration_unavailable(SimpleNamespace(rag=SimpleNamespace(retriever=small)))
        )
        no_dense = self._fake_retriever(50_000, dense=False)
        self.assertIsNone(
            ChatService.exploration_unavailable(SimpleNamespace(rag=SimpleNamespace(retriever=no_dense)))
        )
        # 拿不到检索器时也绝不能阻断
        self.assertIsNone(ChatService.exploration_unavailable(SimpleNamespace()))
        self.assertIsNone(ChatService.exploration_unavailable(None))

    def test_excerpt_ends_at_sentence_boundary_and_stays_a_source_substring(self):
        chinese = (
            "（二）发病机制\n有关偏头痛发病机制尚不清楚，各种诱因引起发病的机制大体上可概括为"
            "血管源学说和神经源学说两大类。神经源学说认为偏头痛的病变发源地在中枢神经系统。"
        )
        out = excerpt(chinese, 60)
        self.assertIn(out, chinese)
        self.assertLessEqual(len(out), 60)
        self.assertTrue(out.endswith("。"), out)

        english = "Six out of 10 unintended pregnancies end in induced abortion. Abortion is a common health intervention."
        out_en = excerpt(english, 70)
        self.assertIn(out_en, english)
        self.assertLessEqual(len(out_en), 70)
        self.assertTrue(out_en.endswith("."), out_en)
        # When no sentence fits under the cap, Latin text still breaks at a word.
        out_en_small = excerpt(english, 45)
        self.assertIn(out_en_small, english)
        self.assertLessEqual(len(out_en_small), 45)
        self.assertTrue(english.startswith(out_en_small))

    def test_extract_fallback_quotes_are_complete_sentences_not_mid_word_fragments(self):
        from agent.MedicalAgent import MedicalAgent

        analysis = QueryAnalyzer(self.corpus).analyze("头疼的可能是什么导致的")
        text = (
            "偏头痛是一组常见的头痛类型，为发作性神经-血管功能障碍。\n"
            "（二）发病机制\n有关偏头痛发病机制尚不清楚，各种诱因引起发病的机制大体上可概括为"
            "血管源学说和神经源学说两大类。\n"
            "神经源学说认为偏头痛的病变发源地在中枢神经系统。"
        )
        doc = Document(
            id="legacy-headache",
            source_id="legacy",
            entity="偏头痛",
            facet="cause",
            title="偏头痛",
            text=text,
            source_title="历史疾病条目",
            review_status="unreviewed",
            published_at=date.today(),
        )
        agent = MedicalAgent(self.corpus, self.retriever, self.settings)
        draft = agent.extract([Evidence(document=doc, relevance=0.95)], analysis)
        self.assertTrue(draft.claims)
        for claim in draft.claims:
            self.assertIn(claim.quotes[0], doc.text)
            self.assertNotIn("制 有关", claim.quotes[0])

    def test_personal_dose_or_stopping_questions_abstain_instead_of_dosing(self):
        analyzer = QueryAnalyzer(self.corpus)
        for question in ["孩子发烧多少度该吃退烧药", "降压药血压正常了可以自己停药吗"]:
            analysis = analyzer.analyze(question)
            self.assertTrue(analysis.personal_treatment, question)

    def test_cancer_anxiety_question_is_not_out_of_scope_and_has_topics(self):
        analysis = QueryAnalyzer(self.corpus).analyze("我胃胀气、打嗝，会不会是胃癌")
        self.assertFalse(analysis.out_of_scope)
        self.assertTrue(analysis.topic_groups)

    def test_emergency_question_routes_to_emergency(self):
        analysis = QueryAnalyzer(self.corpus).analyze("我胸口突然很疼，喘不上气")
        self.assertTrue(analysis.emergency)
        self.assertIn("喘不上气", analysis.emergency_terms)

    def test_english_detection_and_who_title_cleanup(self):
        self.assertTrue(is_english("Six out of 10 unintended pregnancies end in induced abortion."))
        self.assertFalse(is_english("高血压是指血管压力过高（140/90 mmHg或更高）。"))
        self.assertFalse(is_english(""))
        self.assertEqual(clean_title("WHO 浜嬪疄娓呭崟 路 Abortion"), "WHO 事实清单 · Abortion")

    def test_translation_service_is_inert_offline_and_caches_nothing(self):
        service = TranslationService(self.settings)
        self.assertFalse(service.available)
        self.assertIsNone(service.lookup("anything"))
        result = asyncio.run(service.translate("Abortion is a common health intervention."))
        self.assertIsNone(result)

    def test_model_output_is_tolerated_when_wrapped_in_markdown_or_prose(self):
        """很多 OpenAI 兼容服务商把 JSON 包在 markdown 代码块里，或前后加一句说明。

        线上真实故障：某账户用自己的 DeepSeek key 提问，连续两次
        「生成或检查步骤不可用：JSONDecodeError」，从未成功过一次；
        而同期用另一服务商的账户每次都正常。这类传输层格式差异不该让整个回答失败 ——
        解开之后仍要过 pydantic 校验、引用核对与独立语义复核，医学安全约束一条都没放松。
        """
        import json as _json

        from ai.LLMService import LLMService

        service = LLMService.__new__(LLMService)  # 只测解析，不建连接
        service.model = "deepseek-flash"
        service.base_url = "https://api.deepseek.com"

        payload = {"answer": [{"text": "高血压需长期管理。", "support_ids": [1]}]}
        raw = _json.dumps(payload, ensure_ascii=False)
        self.assertEqual(service._loads(raw, "stop"), payload)
        self.assertEqual(service._loads("```json\n" + raw + "\n```", "stop"), payload)
        self.assertEqual(service._loads("```\n" + raw + "\n```", "stop"), payload)
        self.assertEqual(service._loads("好的，以下是结果：\n" + raw + "\n希望有帮助。", "stop"), payload)

    def test_unparseable_model_output_raises_a_diagnosable_error(self):
        """真正解析不了时必须带上病因，而不是一个光秃秃的 JSONDecodeError。

        原先调用方只能记录 "生成或检查步骤不可用：JSONDecodeError"，
        无法判断是内容为空、被 max_tokens 截断、还是退化成了散文。
        """
        from ai.LLMService import LLMService, ModelOutputError

        service = LLMService.__new__(LLMService)
        service.model = "deepseek-flash"
        service.base_url = "https://api.deepseek.com"

        # 空内容（常见于推理型模型把额度耗在思考上）
        with self.assertRaises(ModelOutputError) as empty:
            service._loads("", "length")
        message = str(empty.exception)
        self.assertIn("finish_reason=length", message)
        self.assertIn("chars=0", message)
        self.assertIn("deepseek-flash", message)
        self.assertIn("api.deepseek.com", message)

        # 被截断的 JSON
        with self.assertRaises(ModelOutputError):
            service._loads('{"answer": [{"text": "高血压需要', "length")

        # 仍是 RuntimeError 子类，既有 except Exception 依然覆盖
        self.assertTrue(issubclass(ModelOutputError, RuntimeError))

    def test_diagnostic_text_never_contains_the_api_key(self):
        """诊断信息会进 trace，必须确认其中不含密钥。"""
        from ai.LLMService import LLMService, ModelOutputError

        service = LLMService.__new__(LLMService)
        service.model = "glm-5.3-flash"
        service.base_url = "https://open.bigmodel.cn/api/paas/v4"
        service.api_key = "sk-SUPER-SECRET-TOKEN-12345"

        with self.assertRaises(ModelOutputError) as caught:
            service._loads("不是 JSON", "stop")
        self.assertNotIn("SUPER-SECRET", str(caught.exception))
        self.assertNotIn("sk-", str(caught.exception))

    def test_provider_failure_reasons_map_to_accurate_user_messages(self):
        """用户看到的原因必须与实际病因一致。

        原先所有 provider 失败都说"调用超时或暂不可用"，把"模型返回无法解析"
        也说成超时，会让人去查网络而不是换模型。
        """
        from agent.GroundedAnswerService import GroundedAnswerService
        from agent.MedicalAgent import _generation_failure_message
        from ai.LLMService import ModelOutputError

        class FakeResponse:
            def __init__(self, status):
                self.status_code = status

        class HTTPStatusError(Exception):
            def __init__(self, status):
                super().__init__("boom")
                self.response = FakeResponse(status)

        self.assertEqual(GroundedAnswerService.provider_reason(ModelOutputError("x")), "model_output")
        self.assertEqual(GroundedAnswerService.provider_reason(TimeoutError("x")), "timeout")
        self.assertEqual(GroundedAnswerService.provider_reason(HTTPStatusError(401)), "auth")
        self.assertEqual(GroundedAnswerService.provider_reason(HTTPStatusError(429)), "rate_limited")
        self.assertEqual(GroundedAnswerService.provider_reason(HTTPStatusError(500)), "http_status")
        self.assertEqual(GroundedAnswerService.provider_reason(ConnectionError("x")), "network")

        message = _generation_failure_message(
            [{"attempt": 2, "stage": "provider", "reason": "model_output", "feedback": ["x"]}]
        )
        self.assertIn("无法按约定格式解析", message)
        self.assertIn("更换模型", message)
        self.assertNotIn("超时", message)

        auth = _generation_failure_message(
            [{"attempt": 1, "stage": "provider", "reason": "auth", "feedback": ["x"]}]
        )
        self.assertIn("API Key", auth)

        # 没有 reason 时回落到阶段文案，既有行为不变
        legacy = _generation_failure_message([{"attempt": 1, "stage": "citations", "feedback": ["x"]}])
        self.assertIn("引用", legacy)
