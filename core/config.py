from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:password@localhost/flipkart_verify"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    GEMINI_API_KEY: str = ""
    LOG_LEVEL: str = "DEBUG"  # DEBUG | INFO | WARNING | ERROR
    CSV_IMPORT_WORKERS: int = 4        # parallel DB connections for bulk CSV import (tune to your disk/Postgres setup)
    CSV_IMPORT_CHUNK_SIZE: int = 2_000_000  # rows per chunk (lower = less RAM, more chunks)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
