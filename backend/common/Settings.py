from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MED_",
        env_file=ROOT / ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        populate_by_name=True,
    )
    data_dir: Path = PROJECT / "data"
    reports_dir: Path = PROJECT / "reports"
    frontend_dir: Path = PROJECT / "frontend" / "dist"
    host: str = "127.0.0.1"
    port: int = 8010
    allowed_origins: str = (
        "http://127.0.0.1:8010,http://localhost:8010,http://127.0.0.1:5180,http://localhost:5180"
    )
    secure_cookie: bool = False
    model_key_secret: str = Field(default="", repr=False)
    user_model_base_urls: str = "https://api.deepseek.com,https://api.deepseek.com/v1,https://open.bigmodel.cn/api/paas/v4,https://opencode.ai/zen/go/v1,https://api.openai.com/v1"
    session_days: int = Field(default=7, ge=1, le=30)
    provider: Literal["extractive", "compatible"] = "extractive"
    llm_base_url: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_model: str = ""
    llm_provider: Literal["glm", "deepseek"] = Field(default="glm", validation_alias="LLM_PROVIDER")
    glm_api_key: str = Field(default="", validation_alias="GLM_API_KEY", repr=False)
    glm_model: str = Field(default="glm-4.5-air", validation_alias="GLM_MODEL")
    glm_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4/", validation_alias="GLM_BASE_URL"
    )
    deepseek_api_key: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY", "CHAT_OPENAI_API_KEY"), repr=False
    )
    deepseek_model: str = Field(default="deepseek-v4-flash", validation_alias="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    agent_api_key: str = Field(default="", validation_alias="OPENCODE_API_KEY", repr=False)
    agent_base_url: str = Field(default="https://opencode.ai/zen/go/v1", validation_alias="AGENT_BASE_URL")
    agent_model: str = Field(default="deepseek-v4-flash", validation_alias="AGENT_MODEL")
    llm_timeout: float = Field(default=20, ge=1, le=120)
    max_iterations: int = Field(default=3, ge=1, le=3)
    max_model_calls: int = Field(default=6, ge=1, le=10)
    # 上限取 600 而非 180：180 是按带 GPU 的开发机（P95 25s）标定的。
    # 部署到 2 vCPU 纯 CPU 主机后，单次检索本身就是 20-22s，再叠加 HyDE、
    # 生成与独立语义复核，180s 会误杀本可正常完成的中等难度问题。
    # 默认值保持 75 不变，仅放宽运维可调边界。
    request_timeout: float = Field(default=75, ge=1, le=600)
    max_concurrent_chats: int = Field(default=10, ge=1, le=50)
    retrieval_k: int = Field(default=16, ge=2, le=40)
    context_k: int = Field(default=8, ge=1, le=10)
    max_source_age_days: int = Field(default=1095, ge=1, le=3650)
    qa_enabled: bool = Field(default=False, validation_alias="MED_QA_ENABLED")
    embedding_model: str = Field(
        default="", validation_alias=AliasChoices("EMBEDDING_MODEL_PATH", "MED_EMBEDDING_MODEL")
    )
    reranker_model: str = Field(
        default="", validation_alias=AliasChoices("RERANKER_MODEL_PATH", "MED_RERANKER_MODEL")
    )
    chroma_path: Path = Field(default=PROJECT / "data" / "chroma", validation_alias="CHROMA_PATH")
    collection_name: str = Field(default="medical_qa", validation_alias="COLLECTION_NAME")
    data_root: Path = Field(default=PROJECT / "data" / "imports", validation_alias="DATA_ROOT")
    model_device: Literal["cpu", "cuda"] = "cpu"
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = Field(default="", repr=False)
    neo4j_database: str = "neo4j"
    neo4j_timeout: float = Field(default=4, ge=1, le=10)
    pubmed_enabled: bool = False
    pubmed_email: str = ""
    # 是否在启动时向云厂商元数据服务查询本机当前公网 IP，并加入 Host 白名单。
    # 按量付费 ECS 的"普通公网 IP"在停止/启动后会被重新分配，写死在
    # MED_ALLOWED_ORIGINS 里的地址随即失效，访问会得到一个没有说明的 400。
    # 打开后重启无需改配置。测试里关掉，避免联网。
    discover_public_host: bool = True
    requests_per_minute: int = Field(default=20, ge=1, le=120)
    redis_url: str = Field(default="", repr=False)
    redis_password: str = Field(default="", validation_alias="REDIS_PASSWORD", repr=False)
    redis_host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(default=0, validation_alias="REDIS_DB")
    redis_enabled: bool = True
    memory_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    memory_recent_turns: int = Field(default=6, ge=1, le=20)
    database_backend: Literal["mysql", "postgres", "sqlite"] = "sqlite"
    mysql_host: str = Field(default="127.0.0.1", validation_alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    mysql_user: str = Field(default="root", validation_alias="MYSQL_USER")
    mysql_password: str = Field(default="", validation_alias="MYSQL_PASSWORD", repr=False)
    mysql_database: str = Field(default="medical_agentic_rag", validation_alias="MYSQL_DATABASE")
    jwt_secret: str = Field(
        default="", validation_alias=AliasChoices("SECRET_KEY", "MED_JWT_SECRET"), repr=False
    )
    jwt_minutes: int = Field(default=120, ge=5, le=43200, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    postgres_dsn: str = Field(default="", repr=False)
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_user: str = Field(default="postgres", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="", validation_alias="POSTGRES_PASSWORD", repr=False)
    postgres_database: str = Field(default="medical_agentic_rag", validation_alias="POSTGRES_DATABASE")

    @property
    def origins(self) -> set[str]:
        return {x.strip() for x in self.allowed_origins.split(",") if x.strip()}

    @model_validator(mode="after")
    def check_provider(self):
        if self.agent_api_key and not self.agent_base_url.startswith(
            ("https://", "http://127.0.0.1:", "http://localhost:")
        ):
            raise ValueError("Agent endpoint must use HTTPS or loopback HTTP")
        if self.provider == "compatible":
            if self.llm_provider == "glm":
                self.llm_base_url = self.llm_base_url or self.glm_base_url
                self.llm_model = self.llm_model or self.glm_model
                self.llm_api_key = self.llm_api_key or self.glm_api_key
            else:
                self.llm_base_url = self.llm_base_url or self.deepseek_base_url
                self.llm_model = self.llm_model or self.deepseek_model
                self.llm_api_key = self.llm_api_key or self.deepseek_api_key
            if not self.llm_base_url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
                raise ValueError("MED_LLM_BASE_URL must use HTTPS or a loopback HTTP endpoint")
            if not self.llm_model or not self.llm_api_key:
                raise ValueError("Configure GLM_API_KEY or DEEPSEEK_API_KEY for the selected LLM_PROVIDER")
        if self.redis_enabled and not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
        if not self.redis_enabled:
            self.redis_url = ""
        return self
