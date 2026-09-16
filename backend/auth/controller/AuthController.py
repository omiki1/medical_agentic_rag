from common.JWTDecode import get_current_user
from fastapi import APIRouter, Depends, Request, Response
from user.entity.UserEntity import LoginEntity


class AuthController:
    def __init__(self, service, user_service, settings):
        self.service, self.user_service, self.settings = service, user_service, settings
        self.router = APIRouter(tags=["auth"])
        self.router.add_api_route("/login", self.login, methods=["POST"])
        self.router.add_api_route("/guestLogin", self.guest, methods=["POST"])
        self.router.add_api_route("/logout", self.logout, methods=["POST"])
        self.session_router = APIRouter(tags=["auth"])
        self.session_router.add_api_route("/session", self.session, methods=["GET"])

    def cookie(self, response, token):
        response.set_cookie(
            "mediatlas_session",
            token,
            httponly=True,
            samesite="strict",
            secure=self.settings.secure_cookie,
            max_age=self.settings.session_days * 86400,
            path="/",
        )

    def login(self, body: LoginEntity, request: Request, response: Response):
        cookie, session, token = self.service.login(body, request.client.host if request.client else "local")
        self.cookie(response, cookie)
        return {
            "code": 200,
            "msg": "登录成功",
            "data": token,
            "csrf": session["csrf"],
            "user": self.user_service.profile(session),
        }

    def guest(self, response: Response):
        cookie, session = self.service.dao.issue_session()
        self.cookie(response, cookie)
        return {"code": 200, "msg": "已建立独立访客会话", "data": None, "csrf": session["csrf"]}

    def logout(self, response: Response, user=Depends(get_current_user)):
        self.service.dao.revoke(user["id"])
        response.delete_cookie("mediatlas_session", path="/")
        return {"code": 200, "msg": "已退出登录", "data": None}

    def session(self, request: Request, response: Response):
        session = self.service.dao.find_session(request.cookies.get("mediatlas_session"))
        if not session:
            cookie, session = self.service.dao.issue_session()
            self.cookie(response, cookie)
        return {
            "csrf": session["csrf"],
            "expires": session["expires"],
            "user": self.user_service.profile(session),
            "mode": "account" if session.get("account_id") else "private_device_session",
        }
