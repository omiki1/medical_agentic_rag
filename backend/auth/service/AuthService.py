import secrets
import time
from collections import defaultdict, deque

from common.HashPwdUtil import PasswordManager
from fastapi import HTTPException


class AuthService:
    def __init__(self, dao, users, settings):
        self.dao, self.users, self.settings = dao, users, settings
        self.signing_key = settings.jwt_secret or secrets.token_urlsafe(48)
        self.attempts = defaultdict(deque)

    def login(self, entity, peer):
        now = time.monotonic()
        for key in list(self.attempts):
            if not self.attempts[key] or self.attempts[key][-1] < now - 60:
                del self.attempts[key]
        queue = self.attempts[peer]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= 8:
            raise HTTPException(429, "登录尝试过于频繁，请稍后重试")
        queue.append(now)
        user = self.users.find_by_email(entity.email)
        if not user or not PasswordManager.verify_password(entity.password, user["password_hash"]):
            raise HTTPException(401, "邮箱或密码错误")
        cookie, session = self.dao.issue_session(user["users_id"])
        from jose import jwt

        token = jwt.encode(
            {
                "sub": session["id"],
                "user_id": user["users_id"],
                "username": user["username"],
                "role_name": user["role_name"],
                "iat": int(time.time()),
                "exp": int(time.time()) + self.settings.jwt_minutes * 60,
                "jti": session["csrf"],
                "iss": "mediatlas",
                "aud": "mediatlas-api",
            },
            self.signing_key,
            algorithm="HS256",
        )
        return cookie, session, token

    def current(self, request):
        auth = request.headers.get("authorization", "")
        bearer = auth.startswith("Bearer ")
        if bearer:
            from jose import JWTError, jwt

            try:
                payload = jwt.decode(
                    auth[7:],
                    self.signing_key,
                    algorithms=["HS256"],
                    audience="mediatlas-api",
                    issuer="mediatlas",
                )
                session = self.dao.get_by_id(payload["sub"])
                if session and not secrets.compare_digest(str(payload.get("jti", "")), session["csrf"]):
                    session = None
            except (JWTError, KeyError):
                raise HTTPException(401, "登录已过期，请重新登录")
        else:
            session = self.dao.find_session(request.cookies.get("mediatlas_session"))
        if not session:
            raise HTTPException(401, "会话已过期，请刷新或重新登录")
        if not bearer and request.method in {"POST", "PATCH", "DELETE"}:
            if not secrets.compare_digest(request.headers.get("X-MediAtlas-CSRF", ""), session["csrf"]):
                raise HTTPException(403, "请求校验失败，请刷新页面重试")
        return session
