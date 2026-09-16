import base64
import copy
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class ModelSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(default="", max_length=4096, repr=False)


class UserModelService:
    """Account-scoped encrypted credentials and request-local LLM clients."""

    # Curated for this application's OpenAI-compatible Chat Completions + JSON contract.
    # Keep labels user-facing and IDs exact. Provider pages may offer additional models
    # through incompatible Responses/Messages endpoints, which are intentionally omitted.
    PROVIDERS = (
        {
            "id": "opencode_go",
            "name": "OpenCode Go",
            "base_urls": ("https://opencode.ai/zen/go/v1",),
            "models": (
                ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash（推荐）"),
                ("deepseek-v4-flash", "DeepSeek V4 Flash"),
                ("deepseek-v4-pro", "DeepSeek V4 Pro"),
                ("glm-5.3-flash", "GLM-5.3-Flash"),
                ("glm-5.3", "GLM-5.3"),
            ),
        },
        {
            "id": "deepseek",
            "name": "DeepSeek 官方 API",
            "base_urls": ("https://api.deepseek.com", "https://api.deepseek.com/v1"),
            "models": (
                ("deepseek-flash", "DeepSeek V4.1 Flash（推荐）"),
            ),
        },
        {
            "id": "zhipu",
            "name": "智谱 BigModel",
            "base_urls": ("https://open.bigmodel.cn/api/paas/v4",),
            "models": (
                ("glm-5.3-flash", "GLM-5.3-Flash（推荐）"),
                ("glm-5.3", "GLM-5.3"),
                ("glm-5.2", "GLM-5.2"),
                ("glm-4.7", "GLM-4.7"),
            ),
        },
        {
            "id": "openai",
            "name": "OpenAI API",
            "base_urls": ("https://api.openai.com/v1",),
            "models": (
                ("gpt-4.1-mini", "GPT-4.1 mini（推荐）"),
                ("gpt-4.1", "GPT-4.1"),
                ("gpt-4o-mini", "GPT-4o mini"),
                ("gpt-4o", "GPT-4o"),
            ),
        },
    )

    def __init__(self, database, settings):
        self.database, self.settings = database, settings

    def cipher(self):
        secret = self.settings.model_key_secret or self.settings.jwt_secret
        if len(secret) < 32:
            raise HTTPException(503, "管理员需先配置至少 32 位的 MED_MODEL_KEY_SECRET")
        return Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(("mediatlas-user-model-v1:" + secret).encode()).digest())
        )

    def row(self, account_id):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT * FROM user_model_settings WHERE account_id=?", (account_id,)
            ).fetchone()

    def allowed(self):
        return [u.strip().rstrip("/") for u in self.settings.user_model_base_urls.split(",") if u.strip()]

    def catalog(self):
        allowed = set(self.allowed())
        result = []
        for provider in self.PROVIDERS:
            base_url = next((url for url in provider["base_urls"] if url in allowed), None)
            if not base_url:
                continue
            result.append(
                {
                    "id": provider["id"],
                    "name": provider["name"],
                    "base_url": base_url,
                    "models": [{"id": model_id, "name": name} for model_id, name in provider["models"]],
                }
            )
        return result

    def provider(self, provider_id):
        return next((provider for provider in self.catalog() if provider["id"] == provider_id), None)

    def provider_for_url(self, base_url):
        for provider in self.PROVIDERS:
            if base_url in provider["base_urls"]:
                return provider["id"]
        return ""

    def public(self, account_id):
        row = self.row(account_id)
        return {
            "configured": bool(row),
            "provider_id": self.provider_for_url(row["base_url"]) if row else "",
            "model": row["model"] if row else "",
            "providers": self.catalog(),
        }

    def validate_url(self, url):
        # Operator-controlled exact URLs prevent user input from accessing internal services.
        if not url.startswith("https://") or url not in self.allowed():
            raise HTTPException(422, "请选择受支持的 HTTPS 模型接口；其他服务需由管理员加入允许列表")

    def save(self, account_id, body):
        provider = self.provider(body.provider_id)
        if not provider:
            raise HTTPException(422, "请选择受支持的模型服务商")
        old = self.row(account_id)
        same_provider_url = (
            old["base_url"]
            if old and self.provider_for_url(old["base_url"]) == provider["id"] and old["base_url"] in self.allowed()
            else None
        )
        url, model = same_provider_url or provider["base_url"], body.model.strip()
        self.validate_url(url)
        allowed_models = {item["id"] for item in provider["models"]}
        if model not in allowed_models:
            raise HTTPException(422, "所选模型不属于该服务商，或尚未通过本系统兼容性配置")
        key = body.api_key.strip()
        if key and (len(key) < 8 or not key.isascii() or any(c.isspace() for c in key)):
            raise HTTPException(422, "API Key 格式不正确")
        if not key and (not old or old["base_url"] != url):
            raise HTTPException(422, "首次配置或更换服务地址时必须填写 API Key")
        encrypted = self.cipher().encrypt(key.encode()).decode() if key else old["encrypted_key"]
        with self.database.connect() as conn:
            if old:
                conn.execute(
                    "UPDATE user_model_settings SET base_url=?,model=?,encrypted_key=? WHERE account_id=?",
                    (url, model, encrypted, account_id),
                )
            else:
                conn.execute(
                    "INSERT INTO user_model_settings VALUES (?,?,?,?)", (account_id, url, model, encrypted)
                )
        return self.public(account_id)

    def delete(self, account_id):
        with self.database.connect() as conn:
            conn.execute("DELETE FROM user_model_settings WHERE account_id=?", (account_id,))
        return {"ok": True}

    def bind(self, account_id, agent):
        from agent.GroundedAnswerService import GroundedAnswerService
        from agent.ReflectionService import ReflectionService
        from ai.LLMService import LLMService

        row = self.row(account_id)
        if not row:
            raise HTTPException(428, "请先在模型设置中填写自己的 API Key 和模型")
        self.validate_url(row["base_url"])
        provider = self.provider(self.provider_for_url(row["base_url"]))
        if not provider or row["model"] not in {item["id"] for item in provider["models"]}:
            raise HTTPException(409, "原模型配置已不在兼容清单中，请重新选择服务商和模型")
        try:
            key = self.cipher().decrypt(row["encrypted_key"].encode()).decode()
        except InvalidToken as error:
            raise HTTPException(409, "模型凭据已失效，请重新保存 API Key") from error
        settings = self.settings.model_copy(
            update={
                "provider": "compatible",
                "llm_api_key": key,
                "llm_base_url": row["base_url"],
                "llm_model": row["model"],
                "agent_api_key": key,
                "agent_base_url": row["base_url"],
                "agent_model": row["model"],
            }
        )
        bound = copy.copy(agent)  # Reuse read-only retrieval models, never mutate the shared agent.
        bound.settings = settings
        # Source display uses cached translations only; no platform-funded translation calls.
        bound.translator = None
        bound.gateway = LLMService(settings)
        bound.agent_gateway = LLMService(settings, role="agent")
        bound.reflection = ReflectionService(settings, bound.agent_gateway)
        bound.answers = GroundedAnswerService(bound.gateway, bound.agent_gateway, settings)
        return bound
