from rag.entity.Evidence import Evidence


class GraphRetriever:
    def __init__(self, corpus):
        self.corpus = corpus

    def retrieve(self, analysis, include_unreviewed=False):
        from agent.QueryAnalyzer import FACET_RELATIONS

        relations = [r for facet in analysis.facets for r in FACET_RELATIONS.get(facet, [])]
        result = {}
        for entity in analysis.entities:
            for row in self.corpus.graph(entity, relations, 80):
                doc = self.corpus.documents[row["doc_id"]]
                if not include_unreviewed and doc.review_status != "source_checked":
                    continue
                ev = result.setdefault(doc.id, Evidence(document=doc, methods=["graph"]))
                ev.graph_paths.append([row["subject"], row["relation"], row["object"]])
        return list(result.values())
