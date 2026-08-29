from __future__ import annotations

import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from smart_email_manager.cli.config import CliConfigError, load_cli_config
from smart_email_manager.cli.main import app


def _clear_config_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SEM_API_URL",
        "SEM_CA_BUNDLE",
        "SEM_CONFIG_FILE",
        "SEM_HTTP_TIMEOUT",
        "SEM_TOKEN",
        "SEM_TOKEN_FILE",
        "SEM_TOKEN_INPUT",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_cli_config_init_show_and_secure_token_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_config_environment(monkeypatch)
    config_path = tmp_path / "config.toml"
    runner = CliRunner()

    initialized = runner.invoke(
        app,
        ["--config", str(config_path), "config", "init", "--api-url", "http://127.0.0.1:9000"],
    )
    assert initialized.exit_code == 0
    assert config_path.is_file()
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert "token" not in config_path.read_text(encoding="utf-8")

    shown = runner.invoke(app, ["--config", str(config_path), "config", "show", "--output", "json"])
    assert shown.exit_code == 0
    assert '"api_url": "http://127.0.0.1:9000"' in shown.stdout
    assert '"token_configured": false' in shown.stdout

    token_result = runner.invoke(
        app,
        ["--config", str(config_path), "config", "token-set"],
        env={"SEM_TOKEN_INPUT": "test-cli-token"},
    )
    assert token_result.exit_code == 0
    assert "test-cli-token" not in token_result.stdout
    loaded = load_cli_config(config_path)
    assert loaded.token == "test-cli-token"
    assert loaded.token_file is not None
    assert stat.S_IMODE(loaded.token_file.stat().st_mode) == 0o600


def test_cli_config_environment_overrides_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_config_environment(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[client]\napi_url = "http://127.0.0.1:8000"\ntimeout_seconds = 60\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SEM_API_URL", "https://mail.example.test")
    monkeypatch.setenv("SEM_HTTP_TIMEOUT", "12")
    monkeypatch.setenv("SEM_TOKEN", "environment-token")

    loaded = load_cli_config(config_path)
    assert loaded.api_url == "https://mail.example.test"
    assert loaded.timeout_seconds == 12
    assert loaded.token == "environment-token"


def test_cli_config_rejects_plaintext_token_and_insecure_token_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_config_environment(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_path.write_text('[client]\ntoken = "must-not-live-here"\n', encoding="utf-8")
    with pytest.raises(CliConfigError, match="unknown client settings"):
        load_cli_config(config_path)

    token_path = tmp_path / "token"
    token_path.write_text("secret\n", encoding="utf-8")
    token_path.chmod(0o644)
    config_path.write_text(f'[client]\ntoken_file = "{token_path}"\n', encoding="utf-8")
    with pytest.raises(CliConfigError, match="permissions must be 0600"):
        load_cli_config(config_path)


def test_cli_connection_failure_is_concise(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_config_environment(monkeypatch)
    result = CliRunner().invoke(
        app,
        ["--api-url", "http://127.0.0.1:9", "--timeout", "1", "system", "health"],
    )
    assert result.exit_code == 3
    assert "Traceback" not in result.output
    assert "Connection refused" in result.output or "connect" in result.output.lower()
