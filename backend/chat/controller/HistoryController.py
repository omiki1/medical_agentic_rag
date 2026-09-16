from uuid import UUID

from common.JWTDecode import get_current_owner, get_current_user, is_admin
from common.ResponsePresentation import ResponsePresentation
from fastapi import APIRouter, Depends, Request

from chat.entity.ChatEntity import ConversationTitleEntity


class HistoryController:
    def __init__(self, service):
        self.service = service
        self.router = APIRouter(tags=["history"])
        self.router.add_api_route("/conversations", self.list, methods=["GET"])
        self.router.add_api_route("/conversations", self.create, methods=["POST"], status_code=201)
        self.router.add_api_route("/conversations/{cid}", self.get, methods=["GET"])
        self.router.add_api_route("/conversations/{cid}", self.rename, methods=["PATCH"])
        self.router.add_api_route("/conversations/{cid}", self.delete, methods=["DELETE"])
        self.router.add_api_route("/runs/{rid}", self.run, methods=["GET"])

    def list(self, owner=Depends(get_current_owner)):
        return self.service.list(owner)

    def create(self, owner=Depends(get_current_owner)):
        return self.service.create(owner)

    def get(self, cid: UUID, request: Request, user=Depends(get_current_user)):
        data = self.service.get(user["id"], cid)
        return data if is_admin(request, user) else ResponsePresentation.conversation(data)

    def rename(self, cid: UUID, body: ConversationTitleEntity, owner=Depends(get_current_owner)):
        return self.service.rename(owner, cid, body.title)

    def delete(self, cid: UUID, owner=Depends(get_current_owner)):
        return self.service.delete(owner, cid)

    def run(self, rid: UUID, request: Request, user=Depends(get_current_user)):
        data = self.service.run(user["id"], rid)
        return data if is_admin(request, user) else ResponsePresentation.run(data)
