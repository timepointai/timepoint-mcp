from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Transport
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8000

    # Downstream services
    FLASH_URL: str = "https://flash.timepointai.com"
    # FLASH_OUTBOUND_KEY is the key MCP sends to Flash as X-Service-Key.
    # Falls back to legacy FLASH_SERVICE_KEY for backward compatibility.
    FLASH_OUTBOUND_KEY: str = ""
    FLASH_SERVICE_KEY: str = ""  # legacy alias — prefer FLASH_OUTBOUND_KEY
    FLASH_ADMIN_KEY: str = ""

    CLOCKCHAIN_URL: str = ""
    CLOCKCHAIN_SERVICE_KEY: str = ""

    BILLING_URL: str = ""
    BILLING_SERVICE_KEY: str = ""

    GATEWAY_URL: str = ""
    GATEWAY_SERVICE_KEY: str = ""

    # Auth & key store
    DATABASE_URL: str = ""
    MCP_SIGNING_SECRET: str = ""

    # Rate limits — read (requests per minute)
    RATE_LIMIT_ANONYMOUS: int = 30
    RATE_LIMIT_FREE: int = 60
    RATE_LIMIT_EXPLORER: int = 60
    RATE_LIMIT_CREATOR: int = 300
    RATE_LIMIT_STUDIO: int = 1000

    # Rate limits — write (requests per minute)
    RATE_LIMIT_WRITE_FREE: int = 5
    RATE_LIMIT_WRITE_EXPLORER: int = 10
    RATE_LIMIT_WRITE_CREATOR: int = 30
    RATE_LIMIT_WRITE_STUDIO: int = 100

    @property
    def flash_outbound_key(self) -> str:
        """Key sent to Flash as X-Service-Key. Prefers FLASH_OUTBOUND_KEY, falls back to FLASH_SERVICE_KEY."""
        return self.FLASH_OUTBOUND_KEY or self.FLASH_SERVICE_KEY

    model_config = {"env_file": ".env", "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
