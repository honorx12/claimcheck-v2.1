"""All settings come from env (or backend/.env). No secrets in code (SEC-3)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"                       # "prod" disables /docs, /openapi.json
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Neon Postgres (pgvector) + Neon Auth (JWT via JWKS)
    DATABASE_URL: str
    DB_POOL_MAX: int = 8
    NEON_AUTH_BASE_URL: str
    NEON_AUTH_JWKS_URL: str

    # S3-compatible bucket (private)
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_ENDPOINT_URL_S3: str
    AWS_REGION: str = "auto"
    BUCKET: str = "claim-docs"

    # NVIDIA Nemotron, OpenAI-compatible HTTP API. Model id: copy exact id from build.nvidia.com
    NVIDIA_API_KEY: str
    NVIDIA_MODEL: str
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    LLM_TIMEOUT_S: float = 60
    LLM_ATTEMPTS: int = 3
    LLM_BACKOFF_S: float = 1.0
    LLM_MAX_TOKENS: int = 2048

    # Limits (PRD NFR-2: proposals, tune after measuring)
    MAX_FILE_BYTES: int = 10 * 1024 * 1024
    MAX_PAGES: int = 30
    MAX_QUESTION_CHARS: int = 500
    ANALYSES_PER_HOUR: int = 10
    UPLOADS_PER_HOUR: int = 20
    CRAG_MAX_RETRIES: int = 2
    RETENTION_DAYS: int = 30               # placeholder: decide with counsel
    STALE_PROCESSING_MIN: int = 10

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"


settings = Settings()
