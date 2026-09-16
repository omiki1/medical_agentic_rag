import asyncio
import unittest
from types import SimpleNamespace

from agent.MedicalAgent import MedicalAgent
from rag.entity.Evidence import Document, Evidence

from tests.test_contracts import Fixtures


class ModeContracts(Fixtures):
    def test_unreviewed_material_is_usable_only_in_exploration(self):
        document = Document(
            id="legacy-test-department",
            source_id="legacy-test",
            entity="高血压",
            facet="department",
            title="高血压的就诊科室",
            text="高血压相关问题可以在心血管内科进行评估。",
            source_title="历史疾病条目（测试夹具）",
        )
        retrieval = SimpleNamespace(
            warnings=[],
            dense=None,
            hybrid=lambda query, k=None, mode="authoritative": [
                Evidence(document=document, methods=["bm25"])
            ],
        )
        agent = MedicalAgent(self.corpus, retrieval, self.settings)
        strict = asyncio.run(agent.run("高血压挂什么科", mode="authoritative"))
        broad = asyncio.run(agent.run("高血压挂什么科", mode="exploratory"))
        self.assertEqual(strict.status, "abstained")
        self.assertEqual(broad.status, "answered")
        self.assertTrue(broad.answer_grade.passed)
        self.assertEqual(broad.mode, "exploratory")
        self.assertNotIn("探索模式：", broad.answer)
        self.assertIn(document.text, broad.answer)

    def test_both_modes_preserve_emergency_and_individual_prescribing_limits(self):
        agent = MedicalAgent(self.corpus, self.retriever, self.settings)
        for mode in ["authoritative", "exploratory"]:
            self.assertEqual(asyncio.run(agent.run("我现在胸痛喘不过气", mode=mode)).status, "emergency")
            self.assertEqual(
                asyncio.run(agent.run("糖尿病二甲双胍吃多少毫克", mode=mode)).status, "abstained"
            )


if __name__ == "__main__":
    unittest.main()
