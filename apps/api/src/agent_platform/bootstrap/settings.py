from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_root = Path(__file__).parent.parent.parent.parent.parent.parent
_config_path = _root / "config.toml"


def _load_config() -> dict:
    if _config_path.exists():
        import tomllib

        with open(_config_path, "rb") as f:
            return tomllib.load(f)
    return {}


class Settings(BaseSettings):
    app_name: str = "Agent Operating Platform API"
    api_prefix: str = "/api/v1"
    default_tenant_id: str = "tenant-demo"
    default_user_id: str = "user-demo"
    database_url: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_temperature: float = 0.2
    llm_system_prompt: str = "你是企业级 Agent 平台中的智能助手，回答要准确、结构清晰，并优先引用已知上下文。"
    secret_key: str = "your-secret-key-change-in-production"

    model_config = SettingsConfigDict(env_prefix="AOP_", extra="ignore")

    @classmethod
    def with_config(cls) -> "Settings":
        toml_config = _load_config()
        return cls(**toml_config)


settings = Settings.with_config()
