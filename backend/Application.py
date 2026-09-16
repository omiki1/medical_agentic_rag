import asyncio
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from auth.controller.AuthController import AuthController
from chat.controller.ChatController import ChatController
from chat.controller.HistoryController import HistoryController
from common.ApplicationContext import ApplicationContext
from common.controller.SystemController import SystemController
from common.RequestBoundary import RequestBoundaryMiddleware
from common.Settings import Settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from memory.controller.MemoryController import MemoryController
from rag.controller.KnowledgeController import KnowledgeController
from starlette.middleware.trustedhost import TrustedHostMiddleware
from user.controller.UserController import UserController
from user.controller.ModelSettingsController import ModelSettingsController


class MedicalApplication:
    def __init__(self, settings=None, *, corpus=None, retriever=None):
        self.settings = settings or Settings()
        self.corpus, self.retriever = corpus, retriever

    @staticmethod
    def discovered_hosts(settings, timeout=2.0):
        """把本机当前的公网 IP 加进允许的主机名。

        为什么需要：按量付费 ECS 用的是"普通公网 IP"，**停止再启动会被重新分配**。
        而 MED_ALLOWED_ORIGINS 里写的是部署时的那个地址，于是重启后访问会得到
        一个没有任何说明的 400 —— 线上真实发生过，看起来就像"服务挂了"，
        实际只是 Host 校验不认新地址。

        这里在启动时问一次云厂商元数据服务（阿里云 100.100.100.200，仅内网可达，
        实测容器内也能读到），把当前公网 IP 加进白名单，重启后无需人工改配置。
        拿不到就安静地跳过（短超时 + 全异常吞掉），只依赖显式配置 ——
        绝不因为元数据服务不可用而影响启动。
        """
        if not getattr(settings, "discover_public_host", False):
            return set()
        hosts = set()
        try:
            import urllib.request

            for key in ("eipv4", "public-ipv4"):
                try:
                    with urllib.request.urlopen(
                        f"http://100.100.100.200/latest/meta-data/{key}", timeout=timeout
                    ) as response:
                        value = response.read(64).decode("ascii", "ignore").strip()
                except Exception:
                    continue
                # 字段不存在时元数据服务会返回一段 HTML 404 页面，必须校验格式，
                # 否则会把整段 HTML 当成主机名塞进白名单。
                if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
                    hosts.add(value)
        except Exception:
            pass
        return hosts

    def create(self):
        settings = self.settings

        @asynccontextmanager
        async def lifespan(app):
            context = await asyncio.to_thread(ApplicationContext, settings, self.corpus, self.retriever)
            app.state.context = context
            self.register_controllers(app, context)
            yield
            await asyncio.to_thread(context.close)

        app = FastAPI(title="MediAtlas · 医学证据工作台", version="1.0.0", lifespan=lifespan)
        app.add_middleware(RequestBoundaryMiddleware, settings=settings)
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=sorted(
                {"localhost", "127.0.0.1", "testserver"}
                | {urlparse(o).hostname for o in settings.origins}
                | self.discovered_hosts(settings)
            ),
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(settings.origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-MediAtlas-CSRF", "Authorization"],
        )
        if settings.frontend_dir.exists() and (settings.frontend_dir / "index.html").exists():
            if (settings.frontend_dir / "assets").exists():
                app.mount("/assets", StaticFiles(directory=settings.frontend_dir / "assets"), name="assets")
            app.add_api_route(
                "/", lambda: FileResponse(settings.frontend_dir / "index.html"), include_in_schema=False
            )
            app.add_api_route(
                "/favicon.svg",
                lambda: FileResponse(settings.frontend_dir / "favicon.svg"),
                include_in_schema=False,
            )
        return app

    @staticmethod
    def register_controllers(app, ctx):
        auth = AuthController(ctx.auth_service, ctx.user_service, ctx.settings)
        chat = ChatController(ctx.chat_service)
        app.include_router(auth.router, prefix="/auth")
        app.include_router(auth.session_router, prefix="/api")
        app.include_router(UserController(ctx.user_service).router, prefix="/users")
        app.include_router(ModelSettingsController(ctx.user_model_service).router, prefix="/api")
        app.include_router(chat.router, prefix="/chat")
        app.include_router(chat.router, prefix="/api")
        app.include_router(HistoryController(ctx.history_service).router, prefix="/api")
        app.include_router(MemoryController(ctx.memory_service, ctx.settings).router, prefix="/api")
        app.include_router(
            KnowledgeController(ctx.knowledge_service, ctx.corpus, ctx.neo4j, ctx.translator).router,
            prefix="/api",
        )
        app.include_router(SystemController(ctx).router, prefix="/api")
