from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    environment: str = Field(default="development")
    database_url: str = Field(min_length=10)
    secret_key: str = Field(min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=480, ge=5, le=1440)

    rate_limit_per_minute: int = Field(default=60, ge=1)
    max_upload_size_mb: int = Field(default=10, ge=1, le=50)
    allowed_origins: list[str] = Field(default=["http://localhost:3000"])
    allowed_file_extensions: list[str] = Field(default=[".pdf", ".xlsx", ".csv"])

    alert_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: str = ""

    @field_validator("secret_key")
    @classmethod
    def secret_key_not_default(cls, v: str) -> str:
        forbidden = {"changeme", "secret", "password", "12345", "condodata"}
        if v.lower() in forbidden:
            raise ValueError("secret_key no puede ser un valor por defecto")
        return v

    @field_validator("environment")
    @classmethod
    def environment_valid(cls, v: str) -> str:
        if v not in {"development", "staging", "production"}:
            raise ValueError("environment debe ser development, staging o production")
        return v


settings = Settings()  # type: ignore[call-arg]
