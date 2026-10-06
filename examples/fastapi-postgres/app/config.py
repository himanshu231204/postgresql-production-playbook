"""Application settings, read from environment variables (and a local .env)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fastapi-postgres"

    # Required. No default: the app must not start with a guessed credential.
    database_url: SecretStr

    # Pool settings are per process. Worst-case server connections =
    # workers * (db_pool_size + db_max_overflow).
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout: float = Field(default=10.0, gt=0)
    db_pool_recycle: int = Field(default=1800, ge=-1)
    db_pool_pre_ping: bool = True

    db_connect_timeout: float = Field(default=10.0, gt=0)
    db_statement_timeout_ms: int = Field(default=15_000, ge=0)

    # When set, verify the server certificate and host name (verify-full).
    db_ssl_ca_file: str | None = None

    # PgBouncer transaction mode without prepared-statement tracking.
    db_use_null_pool: bool = False
    db_disable_statement_cache: bool = False

    db_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
