class KnowledgeService:
    def __init__(self, corpus, qa=None):
        self.corpus = corpus
        self.qa = qa

    def discover(self, query, limit=20, reviewed_only=False, offset=0):
        query = query.strip().lower()
        matches = (
            d
            for d in self.corpus.documents.values()
            if (not reviewed_only or d.review_status == "source_checked")
            and (not query or query in d.title.lower() or query in " ".join(d.aliases).lower())
        )
        results = sorted(matches, key=lambda d: (d.review_status != "source_checked", d.entity, d.id))
        base = results[offset : offset + limit]
        total = len(results)
        if self.qa and not reviewed_only:
            extra, qa_total = self.qa.discover(query, max(0, limit - len(base)), max(0, offset - total))
            base.extend(extra)
            total += qa_total
        return base, total

    def document(self, doc_id):
        return self.corpus.documents.get(doc_id) or (self.qa.document(doc_id) if self.qa else None)
