import unittest

from create_data.QADocumentBuilder import QADocumentBuilder
from create_data.WHOCollector import build_documents


class IngestionContracts(unittest.TestCase):
    def test_who_overview_fallback_keeps_entity_chunks_and_unknown_date(self):
        documents = build_documents(
            "test", {"entity": "测试疾病", "description": "公开来源概述文本。" * 130}, []
        )
        self.assertGreater(len(documents), 1)
        self.assertEqual(len({doc["id"] for doc in documents}), len(documents))
        for doc in documents:
            self.assertEqual(doc["entity"], "测试疾病")
            self.assertEqual(doc["facet"], "overview")
            self.assertIsNone(doc["published_at"])
            self.assertEqual(doc["date_provenance"], "publication_not_extracted")

    def test_holdout_partitions_are_excluded(self):
        for source in ["test", "test_zh_0", "valid", "validation", "", "unknown"]:
            docs, reason = QADocumentBuilder.build(
                {"source": source, "prompt": "问题", "response": "回答"}, "data.jsonl", 1
            )
            self.assertEqual(docs, [])
            self.assertEqual(reason, "excluded_split")

    def test_only_chosen_reward_answer_is_imported(self):
        docs, reason = QADocumentBuilder.build(
            {
                "source": "train",
                "question": "问题",
                "response_chosen": "被选择的训练答案。",
                "response_rejected": "禁止入库的拒绝答案。",
            },
            "reward.jsonl",
            12,
        )
        self.assertEqual(reason, "accepted")
        self.assertNotIn("禁止入库", docs[0].text)
        self.assertEqual(docs[0].review_status, "unreviewed")
        self.assertEqual(docs[0].source_line, 12)

    def test_identifiers_redacted_and_duplicates_stable(self):
        row = {"source": "train_zh_0", "prompt": "联系13812345678", "response": "邮箱person@example.com"}
        first, _ = QADocumentBuilder.build(row, "first.jsonl", 1)
        second, _ = QADocumentBuilder.build(row, "second.jsonl", 100)
        self.assertEqual(first[0].id, second[0].id)
        self.assertNotIn("13812345678", first[0].text)
        self.assertNotIn("person@example.com", first[0].text)

    def test_empty_answer_is_not_a_document(self):
        docs, reason = QADocumentBuilder.build(
            {"source": "train", "prompt": "问题", "response": ""}, "file.jsonl", 1
        )
        self.assertEqual((docs, reason), ([], "invalid"))


if __name__ == "__main__":
    unittest.main()
