from uuid import UUID

from common.JWTDecode import get_admin_owner
from fastapi import APIRouter, Depends, HTTPException

from memory.entity.MemoryRequest import MemoryRequest


class MemoryController:
    def __init__(self, service, settings):
        self.service, self.settings = service, settings
        self.router = APIRouter(tags=["memory"])
        self.router.add_api_route("/memory", self.list, methods=["GET"])
        self.router.add_api_route("/memory", self.remember, methods=["POST"], status_code=201)
        self.router.add_api_route("/memory/{mid}", self.update, methods=["PATCH"])
        self.router.add_api_route("/memory/{mid}", self.delete, methods=["DELETE"])

    def list(self, owner=Depends(get_admin_owner)):
        return {
            "semantic": self.service.semantic(owner),
            "episodes": self.service.episodes(owner),
            "redis": self.service.redis_status,
            "short_term_ttl": self.settings.memory_ttl_seconds,
            "recent_turns": self.settings.memory_recent_turns,
            "session_days": self.settings.session_days,
        }

    def remember(self, body: MemoryRequest, owner=Depends(get_admin_owner)):
        try:
            return self.service.remember(owner, body.kind, body.value)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    def update(self, mid: UUID, body: MemoryRequest, owner=Depends(get_admin_owner)):
        try:
            return self.service.remember(owner, body.kind, body.value, str(mid))
        except LookupError as error:
            raise HTTPException(404, "未找到记忆") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def delete(self, mid: UUID, owner=Depends(get_admin_owner)):
        if not self.service.forget(owner, str(mid)):
            raise HTTPException(404, "未找到记忆")
        return {"ok": True}
