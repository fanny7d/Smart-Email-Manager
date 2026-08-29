from __future__ import annotations

import json
import os
import stat
import tempfile
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit


class CliConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CliConfig:
    config_path: Path
    api_url: str = "http://127.0.0.1:8000"
    token_file: Path | None = None
    token: str = ""
    timeout_seconds: float = 60.0
    ca_bundle: Path | None = None


def default_config_path() -> Path:
    override = os.getenv("SEM_CONFIG_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    root = (
        Path(os.environ["XDG_CONFIG_HOME"]).expanduser()
        if os.getenv("XDG_CONFIG_HOME")
        else Path.home() / ".config"
    )
    return root / "smart-email-manager" / "config.toml"


def default_token_path(config_path: Path | None = None) -> Path:
    return (config_path or default_config_path()).parent / "token"


def _resolve_file(value: object, *, base: Path, field: str) -> Path | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise CliConfigError(f"{field} must be a file path string")
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _validate_api_url(value: object) -> str:
    if not isinstance(value, str):
        raise CliConfigError("client.api_url must be a string")
    url = value.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise CliConfigError("client.api_url must be an HTTP(S) origin without a path")
    if parsed.username or parsed.password:
        raise CliConfigError("client.api_url must not contain credentials")
    return url


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CliConfigError("client.timeout_seconds must be a number")
    timeout = float(value)
    if not 1 <= timeout <= 600:
        raise CliConfigError("client.timeout_seconds must be between 1 and 600")
    return timeout


def _read_token(path: Path) -> str:
    if not path.is_file():
        raise CliConfigError(f"token file does not exist: {path}")
    metadata = path.stat()
    if metadata.st_size > 65_536:
        raise CliConfigError(f"token file is unexpectedly large: {path}")
    if os.name != "nt":
        if metadata.st_uid != os.getuid():
            raise CliConfigError(f"token file must be owned by the current user: {path}")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise CliConfigError(f"token file permissions must be 0600: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise CliConfigError(f"token file is empty: {path}")
    return token


def load_cli_config(
    config_path: Path | None = None,
    *,
    api_url: str | None = None,
    token_file: Path | None = None,
    timeout_seconds: float | None = None,
    load_token: bool = True,
) -> CliConfig:
    path = (config_path or default_config_path()).expanduser()
    config = CliConfig(config_path=path)
    if path.exists():
        if not path.is_file():
            raise CliConfigError(f"config path is not a file: {path}")
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise CliConfigError(f"cannot read config file {path}: {exc}") from exc
        unknown_sections = set(payload) - {"client"}
        if unknown_sections:
            raise CliConfigError(f"unknown config sections: {', '.join(sorted(unknown_sections))}")
        client = payload.get("client", {})
        if not isinstance(client, dict):
            raise CliConfigError("[client] must be a TOML table")
        allowed = {"api_url", "token_file", "timeout_seconds", "ca_bundle"}
        unknown_keys = set(client) - allowed
        if unknown_keys:
            raise CliConfigError(f"unknown client settings: {', '.join(sorted(unknown_keys))}")
        config = replace(
            config,
            api_url=_validate_api_url(client.get("api_url", config.api_url)),
            token_file=_resolve_file(client.get("token_file"), base=path.parent, field="client.token_file"),
            timeout_seconds=_validate_timeout(client.get("timeout_seconds", config.timeout_seconds)),
            ca_bundle=_resolve_file(client.get("ca_bundle"), base=path.parent, field="client.ca_bundle"),
        )

    resolved_url = api_url or os.getenv("SEM_API_URL")
    if resolved_url:
        config = replace(config, api_url=_validate_api_url(resolved_url))
    resolved_timeout: object = timeout_seconds
    if resolved_timeout is None and os.getenv("SEM_HTTP_TIMEOUT"):
        try:
            resolved_timeout = float(os.environ["SEM_HTTP_TIMEOUT"])
        except ValueError as exc:
            raise CliConfigError("SEM_HTTP_TIMEOUT must be a number") from exc
    if resolved_timeout is not None:
        config = replace(config, timeout_seconds=_validate_timeout(resolved_timeout))

    env_token_file = os.getenv("SEM_TOKEN_FILE", "").strip()
    if token_file is not None:
        config = replace(config, token_file=token_file.expanduser())
    elif env_token_file:
        config = replace(config, token_file=Path(env_token_file).expanduser())
    env_ca_bundle = os.getenv("SEM_CA_BUNDLE", "").strip()
    if env_ca_bundle:
        config = replace(config, ca_bundle=Path(env_ca_bundle).expanduser())
    if config.ca_bundle is not None and not config.ca_bundle.is_file():
        raise CliConfigError(f"CA bundle does not exist: {config.ca_bundle}")

    direct_token = os.getenv("SEM_TOKEN", "").strip()
    token = direct_token or (
        _read_token(config.token_file) if load_token and config.token_file else ""
    )
    return replace(config, token=token)


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)


def write_cli_config(config: CliConfig, *, overwrite: bool) -> None:
    if config.config_path.exists() and not overwrite:
        raise CliConfigError(f"config file already exists: {config.config_path}")
    api_url = _validate_api_url(config.api_url)
    timeout_seconds = _validate_timeout(config.timeout_seconds)
    if config.ca_bundle is not None and not config.ca_bundle.is_file():
        raise CliConfigError(f"CA bundle does not exist: {config.ca_bundle}")
    lines = [
        "[client]",
        f"api_url = {json.dumps(api_url)}",
        f"timeout_seconds = {timeout_seconds:g}",
    ]
    if config.token_file:
        lines.append(f"token_file = {json.dumps(str(config.token_file))}")
    if config.ca_bundle:
        lines.append(f"ca_bundle = {json.dumps(str(config.ca_bundle))}")
    _atomic_write(config.config_path, "\n".join(lines) + "\n", 0o600)


def write_token_file(path: Path, token: str, *, overwrite: bool) -> None:
    value = token.strip()
    if not value:
        raise CliConfigError("token must not be empty")
    if path.exists() and not overwrite:
        raise CliConfigError(f"token file already exists: {path}")
    _atomic_write(path.expanduser(), f"{value}\n", 0o600)
