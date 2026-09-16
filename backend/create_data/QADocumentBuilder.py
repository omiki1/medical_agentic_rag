import re

from rag.entity.Evidence import Document

from create_data.BuildMedicalCorpus import chunks, clean, stable_id


class QADocumentBuilder:
    """Training partitions only; reward rejected answers are never evidence."""

    @staticmethod
    def redact(text):
        text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[电话已隐去]", text)
        text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[证件号已隐去]", text)
        return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐去]", text)

    @classmethod
    def build(cls, row, filename, line):
        split = str(row.get("source", "")).lower()
        if not (split == "train" or split.startswith("train_")):
            return [], "excluded_split"
        question = cls.redact(clean(row.get("prompt") or row.get("question")))
        response = cls.redact(clean(row.get("response_chosen") or row.get("response") or row.get("answer")))
        if not question or not response or len(question) > 4000 or len(response) > 50000:
            return [], "invalid"
        source = "qa:" + stable_id(question, response)
        docs = [
            Document(
                id=stable_id(source, str(index), chunk),
                source_id=source,
                title=question[:120],
                text=f"问题：{question[:1000]}\n回答：{chunk}",
                source_type="qa",
                source_title="shibing624 中文医学 QA（训练语料，待医学复核）",
                source_file=filename,
                source_line=line,
                split=split,
            )
            for index, chunk in enumerate(chunks(response))
        ]
        return docs, "accepted"
