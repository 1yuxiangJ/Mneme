"""Application config loaded from .env via pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- DeepSeek (Awake + Sleep LLM) -----
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ----- Embedding (阿里通义 default;OpenAI-compatible 端口) -----
    embed_api_key: str
    embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_model: str = "text-embedding-v3"
    embed_dimensions: int = 1024

    # ----- Database -----
    database_url: str  # postgresql+asyncpg://userjyx:PWD@localhost:5432/mneme

    # ----- MCP server -----
    mcp_server_host: str = "localhost"
    mcp_server_port: int = 8000
    mcp_server_path: str = "/mcp"

    # ----- Sleep agent -----
    sleep_idle_threshold_seconds: int = 1800
    sleep_scheduler_enabled: bool = False
    sleep_daily_cron_hour: int = 3
    sleep_max_wall_time_seconds: int = 300
    sleep_max_tokens: int = 50000
    sleep_min_archival_count: int = 10

    # ----- Logging -----
    log_level: str = "INFO"
    log_file: str = "logs/mneme.log"

    # ----- User (MVP single user) -----
    user_id: str = "userjyx"


# Singleton — import this everywhere instead of re-instantiating.
# pydantic-settings fills required fields from environment at runtime.
settings = Settings()  # type: ignore[call-arg]
