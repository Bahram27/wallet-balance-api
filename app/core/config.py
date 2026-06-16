from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Wallet Balance API"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/wallet_db"
    REDIS_URL: str = "redis://localhost:6379"

    IDEMPOTENCY_TTL: int = 86400  # 24 hours
    LOCK_TTL: int = 30  # seconds — distributed lock timeout

    class Config:
        env_file = ".env"


settings = Settings()
