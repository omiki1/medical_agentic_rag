import asyncio

from common.JWTDecode import get_admin_owner, get_current_user, is_admin
from common.ResponsePresentation import ResponsePresentation
from fastapi import APIRouter, Depends, HTTPException, Query, Request


class KnowledgeController:
    def __init__(self, service, corpus, graph, translator=None):
        self.service, self.corpus, self.graph = service, corpus, graph
        self.translator = translator
        self.router = APIRouter(tags=["knowledge"])
        self.router.add_api_route("/knowledge", self.search, methods=["GET"])
        self.router.add_api_route("/knowledge/{doc_id:path}", self.document, methods=["GET"])
        self.router.add_api_route("/graph", self.relations, methods=["GET"])

    async def search(
        self,
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=200000),
        reviewed: bool = False,
        owner=Depends(get_admin_owner),
    ):
        items, total = self.service.discover(q, limit, reviewed, offset)
        serialized = [d.model_dump(mode="json") for d in items]
        await self._attach_translations(serialized, cap=5, run_id="knowledge-list")
        return {"items": serialized, "total": total, "offset": offset}

    async def document(self, doc_id: str, request: Request, user=Depends(get_current_user)):
        doc = self.service.document(doc_id)
        if not doc:
            raise HTTPException(404, "未找到来源")
        serialized = [doc.model_dump(mode="json")]
        await self._attach_translations(serialized, cap=1, run_id="knowledge-doc")
        if is_admin(request, user):
            return serialized[0]
        return ResponsePresentation.document(serialized[0])

    async def _attach_translations(self, items, cap: int, run_id: str):
        if not self.translator or not items:
            return
        for item in items:
            row = self.translator.lookup(item.get("text") or "")
            if not row:
                continue
            if row.get("title_zh"):
                item["title_zh"] = row["title_zh"]
            if row.get("text_zh"):
                item["text_zh"] = row["text_zh"]

    async def relations(
        self, entity: str = Query(min_length=1, max_length=100), owner=Depends(get_admin_owner)
    ):
        rows = self.corpus.graph(entity, limit=60)
        try:
            live = await asyncio.to_thread(self.graph.query, [entity], None, 60)
            degraded = False
        except Exception:
            live = []
            degraded = True
        return {
            "entity": entity,
            "edges": rows,
            "neo4j_edges": live,
            "degraded": degraded,
            "note": "图谱缺少记录不表示禁忌，也不能证明用药安全。",
        }
