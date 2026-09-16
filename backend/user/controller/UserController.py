from common.JWTDecode import get_current_user
from fastapi import APIRouter, Depends

from user.entity.UserEntity import RegisterEntity


class UserController:
    def __init__(self, service):
        self.service = service
        self.router = APIRouter(tags=["user"])
        self.router.add_api_route("/register", self.register, methods=["POST"], status_code=201)
        self.router.add_api_route("/profile", self.profile, methods=["GET"])

    def register(self, body: RegisterEntity):
        return self.service.register(body)

    def profile(self, user=Depends(get_current_user)):
        return {"code": 200, "msg": "查询成功", "data": self.service.profile(user)}
