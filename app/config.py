from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Transport
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8000

    # Downstream services
    FLASH_URL: str = "https://api.timepointai.com"
    FLASH_SERVICE_KEY: str = ""
    FLASH_ADMIN_KEY: str = ""

    CLOCKCHAIN_URL: str = ""
    CLOCKCHAIN_SERVICE_KEY: str = ""

    BILLING_URL: str = ""
    BILLING_SERVICE_KEY: str = ""

    PRO_URL: str = ""
    PRO_API_KEY: str = ""

    # Auth & key store
    DATABASE_URL: str = ""
    MCP_SIGNING_SECRET: str = ""

    # Rate limits (requests per minute)
    RATE_LIMIT_ANONYMOUS: int = 30
    RATE_LIMIT_FREE: int = 60
    RATE_LIMIT_EXPLORER: int = 60
    RATE_LIMIT_CREATOR: int = 300
    RATE_LIMIT_STUDIO: int = 1000

    model_config = {"env_file": ".env", "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
