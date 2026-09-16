from common.HashPwdUtil import PasswordManager
from fastapi import HTTPException


class UserService:
    def __init__(self, dao):
        self.dao = dao

    def register(self, entity):
        if self.dao.find_by_email(entity.email):
            raise HTTPException(409, "账号已注册")
        try:
            self.dao.create(entity.username, entity.email, PasswordManager.hash_password(entity.password))
        except Exception as error:
            if self.dao.find_by_email(entity.email):
                raise HTTPException(409, "账号已注册") from error
            raise
        return {"code": 200, "msg": "注册成功", "data": None}

    def profile(self, session):
        return (
            self.dao.find_by_id(session["account_id"])
            if session.get("account_id")
            else {"username": "本地访客", "role_name": "guest"}
        )
