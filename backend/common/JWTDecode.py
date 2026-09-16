from fastapi import HTTPException, Request


def get_current_user(request: Request):
    session = request.app.state.context.auth_service.current(request)
    if not session.get("account_id"):
        raise HTTPException(401, "请先登录账户")
    return session


def get_current_owner(request: Request):
    return get_current_user(request)["id"]


def is_admin(request: Request, session):
    # Always consult the database: client fields and old JWT roles are not authority.
    profile = request.app.state.context.user_service.profile(session)
    return bool(profile and profile.get("role_name") == "admin")


def get_admin_owner(request: Request):
    session = get_current_user(request)
    if not is_admin(request, session):
        raise HTTPException(403, "此功能仅供管理员使用")
    return session["id"]
