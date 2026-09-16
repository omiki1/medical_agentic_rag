def fuse(*routes, k=20, weights=None):
    """Weighted reciprocal-rank fusion, one contribution per document per route.

    A source hit via dense+BM25+graph remains ONE document and ONE publisher.
    """
    weights = weights or {}
    merged = {}
    for route in routes:
        seen = set()
        for rank, ev in enumerate(route, 1):
            doc_id = ev.document.id
            if doc_id in seen:
                continue
            seen.add(doc_id)
            if doc_id not in merged:
                merged[doc_id] = ev.model_copy(deep=True)
                merged[doc_id].fusion_score = 0
                merged[doc_id].fusion_contributions = {}
            item = merged[doc_id]
            contributions = ev.fusion_contributions or {
                (ev.methods[0] if ev.methods else "unknown"): weights.get(
                    ev.methods[0] if ev.methods else "unknown", 1.0
                )
                / (60 + rank)
            }
            for method, contribution in contributions.items():
                item.fusion_contributions[method] = max(
                    item.fusion_contributions.get(method, 0), contribution
                )
            item.fusion_score = sum(item.fusion_contributions.values())
            item.methods = sorted(set(item.methods + ev.methods))
            item.raw_scores.update(ev.raw_scores)
            item.graph_paths = [
                list(x) for x in dict.fromkeys(tuple(p) for p in item.graph_paths + ev.graph_paths)
            ]
    results = sorted(merged.values(), key=lambda e: (-e.fusion_score, e.document.id))[:k]
    for rank, ev in enumerate(results, 1):
        ev.rank = rank
    return results


class EvidenceFusion:
    """按排名融合；每路每份文档只计分一次。"""

    fuse = staticmethod(fuse)
