import asyncio
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
                {"localhost", "127.0.0.1", "testserver"} | {urlparse(o).hostname for o in settings.origins}
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
