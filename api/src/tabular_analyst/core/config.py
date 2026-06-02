from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default="sqlite+pysqlite:///:memory:", alias="DATABASE_URL")
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    ui_dist_dir: Path = Field(default=Path("ui/dist"), alias="UI_DIST_DIR")
    api_auth_token: str | None = Field(default=None, alias="API_AUTH_TOKEN")
    demo_daily_request_limit: int = Field(default=100, alias="DEMO_DAILY_REQUEST_LIMIT")
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    max_rows: int = Field(default=200_000, alias="MAX_ROWS")
    max_columns: int = Field(default=300, alias="MAX_COLUMNS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.1", alias="OPENAI_MODEL")
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173", alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgres_outside_tests(cls, value: str) -> str:
        return value

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_runtime(self) -> None:
        if self.app_env != "test" and not self.api_auth_token:
            raise RuntimeError("API_AUTH_TOKEN is required outside APP_ENV=test.")
        if self.app_env == "production":
            if self.llm_provider != "openai":
                raise RuntimeError("Production requires LLM_PROVIDER=openai.")
            if not self.openai_api_key:
                raise RuntimeError("Production requires OPENAI_API_KEY.")
        if self.app_env not in {"test"} and not self.database_url.startswith("postgresql"):
            raise RuntimeError("Postgres is required outside APP_ENV=test.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
