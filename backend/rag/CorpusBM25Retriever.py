from rag.BM25Retriever import tokenize
from rag.entity.Evidence import Document, Evidence


class CorpusBM25Retriever:
    def __init__(self, corpus, reviewed_only=True):
        self.corpus, self.reviewed_only = corpus, reviewed_only

    def search(self, query, k=16):
        expression = " OR ".join('"' + token + '"' for token in dict.fromkeys(tokenize(query)))
        if not expression:
            return []
        scope = " AND d.review_status='source_checked'" if self.reviewed_only else ""
        with self.corpus.connect() as conn:
            rows = conn.execute(
                "SELECT d.body,bm25(document_search) AS score FROM document_search "
                "JOIN documents d ON d.rowid=document_search.rowid WHERE document_search MATCH ?"
                + scope
                + " ORDER BY score LIMIT ?",
                (expression, k),
            ).fetchall()
        return [
            Evidence(
                document=Document.model_validate_json(row["body"]),
                methods=["bm25"],
                raw_scores={"bm25": -row["score"]},
            )
            for row in rows
        ]
