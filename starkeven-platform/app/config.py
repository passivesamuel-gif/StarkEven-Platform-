from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PLAN_LIMITS = {"starter": 60, "pro": 600, "enterprise": 3000}
TRIAL_CREDITS = 50
_PLACEHOLDERS = ("replace-with", "change-me", "dev-")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # production | development | test

    # Database: either DATABASE_URL, or built from the POSTGRES_* parts.
    database_url_override: str | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str = "starkeven"
    postgres_password: str = "starkeven"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "starkeven"

    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "dev-secret-change-me"
    admin_api_key: str = "dev-admin-key"
    webhook_secret: str = "dev-webhook-secret"
    allowed_origins: str = "http://localhost,http://localhost:3000"
    public_base_url: str = "http://localhost"
    access_token_minutes: int = 1440
    enrich_cache_ttl: int = 86400
    smtp_helo_domain: str = "verify.starkeven.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@starkeven.local"
    demo_lookups_per_hour: int = 5

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            url = self.database_url_override
            if url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            return url
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    def assert_secure(self) -> None:
        """Refuse to start in production with placeholder secrets."""
        if self.environment != "production":
            return
        bad = []
        for name in ("jwt_secret_key", "admin_api_key", "webhook_secret"):
            v = getattr(self, name)
            if len(v) < 32 or v.startswith(_PLACEHOLDERS):
                bad.append(name.upper())
        if not self.database_url_override and (
            self.postgres_password.startswith(_PLACEHOLDERS) or len(self.postgres_password) < 16
        ):
            bad.append("POSTGRES_PASSWORD")
        if bad:
            raise RuntimeError(
                "Insecure configuration for production: " + ", ".join(bad)
                + ". Run ./finalize_prod.sh to generate secrets."
            )


settings = Settings()
