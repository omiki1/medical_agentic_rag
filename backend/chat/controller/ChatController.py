from common.JWTDecode import get_current_user, is_admin
from common.ResponsePresentation import ResponsePresentation
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from chat.entity.ChatEntity import ChatEntity


class ChatController:
    def __init__(self, service):
        self.service = service
        self.router = APIRouter(tags=["chat"])
        self.router.add_api_route("/chat", self.chat, methods=["POST"])

    async def chat(self, body: ChatEntity, request: Request, user=Depends(get_current_user)):
        admin = is_admin(request, user)
        agent = request.app.state.context.user_model_service.bind(user["account_id"], self.service.agent)
        stream = await self.service.chat(body, user["id"], agent=agent)
        if not admin:
            stream = ResponsePresentation.stream(stream)
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )
