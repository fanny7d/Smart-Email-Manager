from __future__ import annotations

import base64
import binascii
import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SEM_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "postgresql+psycopg:///smart_email_manager_dev"
    database_url_file: Path | None = None
    api_token: SecretStr | None = None
    api_token_file: Path | None = None
    master_key: SecretStr | None = None
    master_key_file: Path | None = None
    master_key_version: int = Field(default=1, ge=1)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    worker_id: str = "local-worker-1"
    worker_poll_seconds: float = 2.0
    job_lease_seconds: int = 60

    @field_validator(
        "database_url_file",
        "api_token_file",
        "master_key_file",
        mode="before",
    )
    @classmethod
    def empty_secret_file_path_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def require_production_token(self) -> Settings:
        self.database_url = self._read_file_value(
            self.database_url_file,
            current=self.database_url,
            field_name="SEM_DATABASE_URL_FILE",
        )
        api_token = self._read_file_value(
            self.api_token_file,
            current=self.api_token.get_secret_value() if self.api_token else "",
            field_name="SEM_API_TOKEN_FILE",
        )
        master_key = self._read_file_value(
            self.master_key_file,
            current=self.master_key.get_secret_value() if self.master_key else "",
            field_name="SEM_MASTER_KEY_FILE",
        )
        self.api_token = SecretStr(api_token) if api_token else None
        self.master_key = SecretStr(master_key) if master_key else None
        if self.environment == "production" and not self.api_token:
            raise ValueError("SEM_API_TOKEN is required in production")
        if self.environment == "production" and not self.master_key:
            raise ValueError("SEM_MASTER_KEY is required in production")
        if self.environment == "production" and (
            len(api_token) < 32 or api_token.lower().startswith("replace-with-")
        ):
            raise ValueError("SEM_API_TOKEN must be a non-placeholder value of at least 32 characters")
        if master_key:
            try:
                decoded_master_key = base64.b64decode(
                    master_key.encode("ascii"), altchars=b"-_", validate=True
                )
            except (ValueError, UnicodeError, binascii.Error) as exc:
                raise ValueError("SEM_MASTER_KEY must be URL-safe base64 for 32 bytes") from exc
            if len(decoded_master_key) != 32:
                raise ValueError("SEM_MASTER_KEY must decode to exactly 32 bytes")
        if self.environment == "development" and not self.api_token and not self._is_loopback_host(
            self.api_host
        ):
            raise ValueError(
                "tokenless development is allowed only when SEM_API_HOST is a loopback address"
            )
        self._validate_cors_origins()
        return self

    @staticmethod
    def _is_loopback_host(host: str) -> bool:
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def _validate_cors_origins(self) -> None:
        for origin in self.cors_origins:
            if origin == "*":
                raise ValueError("SEM_CORS_ORIGINS must not contain a wildcard")
            parsed = urlsplit(origin)
            if not parsed.scheme or not parsed.netloc or parsed.path not in {"", "/"}:
                raise ValueError("SEM_CORS_ORIGINS entries must be origins without paths")
            if parsed.username or parsed.password:
                raise ValueError("SEM_CORS_ORIGINS entries must not contain credentials")

    @staticmethod
    def _read_file_value(
        path: Path | None,
        *,
        current: str,
        field_name: str,
    ) -> str:
        if path is None:
            return current
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"{field_name} cannot be read") from exc
        if not value:
            raise ValueError(f"{field_name} is empty")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
