import math
import re
from collections import Counter, defaultdict

from rag.entity.Evidence import Evidence

STOP = set("的 了 和 是 有 在 我 你 请 什么 哪些 怎么 如何 是否 可以 一个 以及 需要 关于".split())


def tokenize(text):
    # Chinese bi-grams preserve exact medical terms without a language-model dependency.
    text = text.lower()
    result = re.findall(r"[a-z0-9]+", text)
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        result.extend(segment[i : i + 2] for i in range(len(segment) - 1) if segment[i : i + 2] not in STOP)
        if len(segment) == 1 and segment not in STOP:
            result.append(segment)
    return result


class BM25Retriever:
    def __init__(self, documents):
        self.documents = {d.id: d for d in documents}
        self.postings = defaultdict(list)
        self.lengths = {}
        for doc in documents:
            tokens = tokenize(doc.title + " " + doc.text)
            self.lengths[doc.id] = len(tokens)
            for token, frequency in Counter(tokens).items():
                self.postings[token].append((doc.id, frequency))
        self.average = sum(self.lengths.values()) / max(1, len(documents))

    def search(self, query, k=16):
        scores = defaultdict(float)
        n = len(self.documents)
        for token in set(tokenize(query)):
            postings = self.postings.get(token, [])
            idf = math.log(1 + (n - len(postings) + 0.5) / (len(postings) + 0.5))
            for doc_id, frequency in postings:
                norm = 1.2 * (1 - 0.75 + 0.75 * self.lengths[doc_id] / max(1, self.average))
                scores[doc_id] += idf * frequency * 2.2 / (frequency + norm)
        return [
            Evidence(document=self.documents[doc_id], methods=["bm25"], raw_scores={"bm25": score})
            for doc_id, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k]
            if score > 0
        ]
