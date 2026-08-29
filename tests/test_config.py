from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from smart_email_manager.config import Settings


def test_production_settings_load_mounted_secret_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SEM_API_TOKEN",
        "SEM_MASTER_KEY",
        "SEM_DATABASE_URL",
        "SEM_API_TOKEN_FILE",
        "SEM_MASTER_KEY_FILE",
        "SEM_DATABASE_URL_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    api_token_file = tmp_path / "api-token"
    master_key_file = tmp_path / "master-key"
    database_url_file = tmp_path / "database-url"
    api_token_file.write_text("mounted-api-token-value-32-characters\n", encoding="utf-8")
    master_key_file.write_text(
        base64.urlsafe_b64encode(b"m" * 32).decode() + "\n",
        encoding="utf-8",
    )
    database_url_file.write_text(
        "postgresql+psycopg://sem_app:secret@db/smart_email_manager\n",
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        environment="production",
        api_token_file=api_token_file,
        master_key_file=master_key_file,
        database_url_file=database_url_file,
    )
    assert settings.api_token is not None
    assert settings.api_token.get_secret_value() == "mounted-api-token-value-32-characters"
    assert settings.master_key is not None
    assert base64.urlsafe_b64decode(settings.master_key.get_secret_value()) == b"m" * 32
    assert settings.database_url.endswith("@db/smart_email_manager")


def test_unreadable_secret_file_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEM_API_TOKEN_FILE", raising=False)
    with pytest.raises(ValidationError, match="SEM_API_TOKEN_FILE cannot be read"):
        Settings(
            _env_file=None,
            api_token_file=tmp_path / "missing",
        )


def test_empty_file_mount_environment_values_are_treated_as_unset() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url_file="",
        api_token_file="  ",
        master_key_file="",
        api_token="p" * 32,
        master_key=base64.urlsafe_b64encode(b"p" * 32).decode(),
    )
    assert settings.database_url_file is None
    assert settings.api_token_file is None
    assert settings.master_key_file is None


def test_tokenless_development_cannot_bind_publicly() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(_env_file=None, environment="development", api_host="0.0.0.0", api_token=None)


def test_production_rejects_placeholder_secrets_and_wildcard_cors() -> None:
    encoded_key = base64.urlsafe_b64encode(b"p" * 32).decode()
    with pytest.raises(ValidationError, match="non-placeholder"):
        Settings(
            _env_file=None,
            environment="production",
            api_token="replace-with-strong-api-token-value",
            master_key=encoded_key,
        )
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(
            _env_file=None,
            environment="production",
            api_token="p" * 32,
            master_key=encoded_key,
            cors_origins=["*"],
        )
