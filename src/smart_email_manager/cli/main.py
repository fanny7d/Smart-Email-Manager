from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import httpx
import typer

from smart_email_manager import __version__
from smart_email_manager.cli.client import SmartEmailManagerClient
from smart_email_manager.cli.config import (
    CliConfig,
    CliConfigError,
    default_config_path,
    default_token_path,
    load_cli_config,
    write_cli_config,
    write_token_file,
)
from smart_email_manager.cli.output import OutputFormat, emit_accounts, emit_json, emit_mapping

app = typer.Typer(
    name="sem",
    help="Smart Email Manager API client",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="Persistent CLI connection configuration")
auth_app = typer.Typer(help="API token management")
system_app = typer.Typer(help="System checks")
fleet_app = typer.Typer(help="Mailbox fleet summary")
groups_app = typer.Typer(help="Hierarchical mailbox groups")
accounts_app = typer.Typer(help="Mailbox account queries")
health_app = typer.Typer(help="Health-check jobs")
imports_app = typer.Typer(help="Write-free import preflight and explicit commit")
jobs_app = typer.Typer(help="Persistent job inspection")
mail_app = typer.Typer(help="Read and mutate mail through the versioned API")
codes_app = typer.Typer(help="Extract recent Outlook verification codes")
proxies_app = typer.Typer(help="Encrypted proxy profiles and assignments")
refresh_app = typer.Typer(help="OAuth token refresh jobs and history")
schedules_app = typer.Typer(help="Persistent worker schedules")
retention_app = typer.Typer(help="Local retained-mail cache")
shares_app = typer.Typer(help="Read-only mailbox share links")
forwarding_app = typer.Typer(help="SMTP forwarding")
security_app = typer.Typer(help="Encryption and security maintenance")
projects_app = typer.Typer(help="Concurrent account work leasing")
audit_app = typer.Typer(help="Security-sensitive operation history")
tags_app = typer.Typer(help="Mailbox tags")
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")
app.add_typer(system_app, name="system")
app.add_typer(fleet_app, name="fleet")
app.add_typer(groups_app, name="groups")
app.add_typer(accounts_app, name="accounts")
app.add_typer(health_app, name="health")
app.add_typer(imports_app, name="imports")
app.add_typer(jobs_app, name="jobs")
app.add_typer(mail_app, name="mail")
app.add_typer(codes_app, name="codes")
app.add_typer(proxies_app, name="proxies")
app.add_typer(refresh_app, name="refresh")
app.add_typer(schedules_app, name="schedules")
app.add_typer(retention_app, name="retention")
app.add_typer(shares_app, name="shares")
app.add_typer(forwarding_app, name="forwarding")
app.add_typer(security_app, name="security")
app.add_typer(projects_app, name="projects")
app.add_typer(audit_app, name="audit")
app.add_typer(tags_app, name="tags")

_runtime_config_path: Path | None = None
_runtime_api_url: str | None = None
_runtime_token_file: Path | None = None
_runtime_timeout_seconds: float | None = None


@app.callback()
def root_options(
    config_file: Annotated[Path | None, typer.Option("--config", envvar="SEM_CONFIG_FILE")] = None,
    api_url: Annotated[str | None, typer.Option("--api-url")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    timeout_seconds: Annotated[float | None, typer.Option("--timeout", min=1, max=600)] = None,
    version: Annotated[
        bool,
        typer.Option("--version", is_eager=True, help="Show CLI version and exit"),
    ] = False,
) -> None:
    global _runtime_config_path, _runtime_api_url, _runtime_token_file, _runtime_timeout_seconds
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    _runtime_config_path = config_file
    _runtime_api_url = api_url
    _runtime_token_file = token_file
    _runtime_timeout_seconds = timeout_seconds


def _client() -> SmartEmailManagerClient:
    try:
        return SmartEmailManagerClient(
            base_url=_runtime_api_url,
            config_path=_runtime_config_path,
            token_file=_runtime_token_file,
            timeout_seconds=_runtime_timeout_seconds,
        )
    except CliConfigError as exc:
        typer.echo(f"CLI configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _handle_http_error(exc: httpx.HTTPError) -> None:
    typer.echo(str(exc), err=True)
    raise typer.Exit(code=3) from exc


def _selected_config_path() -> Path:
    return (_runtime_config_path or default_config_path()).expanduser()


def _config_error(exc: CliConfigError) -> None:
    typer.echo(f"CLI configuration error: {exc}", err=True)
    raise typer.Exit(code=2) from exc


@config_app.command("path")
def config_path(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    path = _selected_config_path()
    emit_mapping(
        {
            "config_file": str(path),
            "exists": path.is_file(),
            "default_token_file": str(default_token_path(path)),
        },
        output,
    )


@config_app.command("init")
def config_init(
    api_url: str = "http://127.0.0.1:8000",
    token_file: Path | None = None,
    timeout_seconds: Annotated[float, typer.Option("--timeout", min=1, max=600)] = 60,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing config file")] = False,
) -> None:
    path = _selected_config_path()
    try:
        config = CliConfig(
            config_path=path,
            api_url=api_url,
            token_file=token_file.expanduser() if token_file else None,
            timeout_seconds=timeout_seconds,
        )
        write_cli_config(config, overwrite=force)
    except CliConfigError as exc:
        _config_error(exc)
    typer.echo(str(path))


@config_app.command("show")
def config_show(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        config = load_cli_config(
            _selected_config_path(),
            api_url=_runtime_api_url,
            token_file=_runtime_token_file,
            timeout_seconds=_runtime_timeout_seconds,
            load_token=False,
        )
    except CliConfigError as exc:
        _config_error(exc)
    token_configured = bool(os.getenv("SEM_TOKEN", "").strip()) or bool(
        config.token_file and config.token_file.is_file() and config.token_file.stat().st_size
    )
    emit_mapping(
        {
            "config_file": str(config.config_path),
            "api_url": config.api_url,
            "token_file": str(config.token_file) if config.token_file else None,
            "token_configured": token_configured,
            "timeout_seconds": config.timeout_seconds,
            "ca_bundle": str(config.ca_bundle) if config.ca_bundle else None,
        },
        output,
    )


@config_app.command("set")
def config_set(
    api_url: str | None = None,
    token_file: Path | None = None,
    timeout_seconds: Annotated[float | None, typer.Option("--timeout", min=1, max=600)] = None,
    ca_bundle: Path | None = None,
) -> None:
    path = _selected_config_path()
    try:
        current = load_cli_config(path, load_token=False)
        updated = replace(
            current,
            api_url=api_url or current.api_url,
            token_file=token_file.expanduser() if token_file else current.token_file,
            timeout_seconds=timeout_seconds or current.timeout_seconds,
            ca_bundle=ca_bundle.expanduser() if ca_bundle else current.ca_bundle,
        )
        write_cli_config(updated, overwrite=True)
        load_cli_config(path, load_token=False)
    except CliConfigError as exc:
        _config_error(exc)
    typer.echo(str(path))


@config_app.command("token-set")
def config_token_set(
    token: Annotated[str | None, typer.Option(envvar="SEM_TOKEN_INPUT", hide_input=True)] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing token file")] = False,
) -> None:
    path = _selected_config_path()
    try:
        config = load_cli_config(path, load_token=False)
        destination = (_runtime_token_file or config.token_file or default_token_path(path)).expanduser()
        resolved_token = token or typer.prompt("API token", hide_input=True)
        write_token_file(destination, resolved_token, overwrite=force)
        if config.token_file != destination:
            write_cli_config(replace(config, token_file=destination), overwrite=True)
    except CliConfigError as exc:
        _config_error(exc)
    typer.echo(str(destination))


@config_app.command("validate")
def config_validate(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            health = client.system_health()
            emit_mapping(
                {
                    "api_url": client.base_url,
                    "authenticated": bool(client.token),
                    "status": health.get("status"),
                    "database": health.get("database"),
                    "version": health.get("version"),
                },
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@auth_app.command("token-create")
def auth_token_create(
    name: str,
    scope: Annotated[list[str] | None, typer.Option("--scope")] = None,
    expires_in_days: Annotated[int | None, typer.Option("--expires-in-days", min=1, max=3650)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_api_token(
                    name=name,
                    scopes=scope or ["*"],
                    expires_in_days=expires_in_days,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@auth_app.command("token-list")
def auth_token_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_api_tokens(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@auth_app.command("token-revoke")
def auth_token_revoke(
    token_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.revoke_api_token(token_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@system_app.command("health")
def system_health(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.system_health(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@fleet_app.command("summary")
def fleet_summary(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.fleet_summary(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@groups_app.command("list")
def groups_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_groups(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@groups_app.command("create")
def groups_create(
    name: str,
    parent_id: uuid.UUID | None = None,
    description: str = "",
    color: str = "#64748b",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_group(
                    name=name,
                    parent_id=parent_id,
                    description=description,
                    color=color,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@groups_app.command("delete")
def groups_delete(group_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            client.delete_group(group_id)
        typer.echo(str(group_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@groups_app.command("update")
def groups_update(
    group_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
    parent_id: uuid.UUID | None = None,
    move_parent: Annotated[bool, typer.Option("--move-parent/--keep-parent")] = False,
    sort_order: int | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.update_group(
                    group_id,
                    name=name,
                    description=description,
                    color=color,
                    parent_id=parent_id,
                    move_parent=move_parent,
                    sort_order=sort_order,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@tags_app.command("list")
def tags_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_tags(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@tags_app.command("create")
def tags_create(
    name: str,
    color: str = "#64748b",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.create_tag(name=name, color=color), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@tags_app.command("delete")
def tags_delete(tag_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            client.delete_tag(tag_id)
        typer.echo(str(tag_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("list")
def accounts_list(
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
    cursor: str | None = None,
    lifecycle: Annotated[str | None, typer.Option("--lifecycle")] = None,
    token: Annotated[str | None, typer.Option("--token-status")] = None,
    mail_health: Annotated[str | None, typer.Option("--mail-health")] = None,
    query: Annotated[str | None, typer.Option("--query", "-q")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    saved_view_id: Annotated[uuid.UUID | None, typer.Option("--saved-view-id")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_accounts(
                client.list_accounts(
                    limit=limit,
                    cursor=cursor,
                    lifecycle_status=lifecycle,
                    token_status=token,
                    mail_health_status=mail_health,
                    query=query,
                    view=view,
                    saved_view_id=saved_view_id,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@fleet_app.command("views")
def fleet_views(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_account_views(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@fleet_app.command("view-create")
def fleet_view_create(
    name: str,
    filters_json: Annotated[str, typer.Option("--filters-json")],
    sort_order: Annotated[int, typer.Option("--sort-order")] = 0,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        filters = json.loads(filters_json)
        if not isinstance(filters, dict):
            raise ValueError("filters must be a JSON object")
        with _client() as client:
            emit_mapping(
                client.create_saved_account_view(
                    name=name,
                    filters=filters,
                    sort_order=sort_order,
                ),
                output,
            )
    except (json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"Invalid --filters-json: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@fleet_app.command("view-update")
def fleet_view_update(
    view_id: uuid.UUID,
    name: str | None = None,
    filters_json: Annotated[str | None, typer.Option("--filters-json")] = None,
    sort_order: Annotated[int | None, typer.Option("--sort-order")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        filters = json.loads(filters_json) if filters_json is not None else None
        if filters is not None and not isinstance(filters, dict):
            raise ValueError("filters must be a JSON object")
        with _client() as client:
            emit_mapping(
                client.update_saved_account_view(
                    view_id,
                    name=name,
                    filters=filters,
                    sort_order=sort_order,
                ),
                output,
            )
    except (json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"Invalid --filters-json: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@fleet_app.command("view-delete")
def fleet_view_delete(view_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            client.delete_saved_account_view(view_id)
        typer.echo(str(view_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("create")
def accounts_create(
    email: str,
    remark: str = "",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_account(
                    email=email,
                    account_type="outlook",
                    provider="outlook",
                    remark=remark,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("secrets-status")
def accounts_secrets_status(
    account_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_account_secrets_status(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("secrets-set")
def accounts_secrets_set(
    account_id: uuid.UUID,
    password: Annotated[
        str | None,
        typer.Option("--password", envvar="SEM_OUTLOOK_PASSWORD", hide_input=True),
    ] = None,
    refresh_token: Annotated[
        str | None,
        typer.Option("--refresh-token", envvar="SEM_OUTLOOK_REFRESH_TOKEN", hide_input=True),
    ] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    if password is None and refresh_token is None:
        typer.echo("Provide --password and/or --refresh-token via hidden prompt or environment.", err=True)
        raise typer.Exit(code=2)
    try:
        with _client() as client:
            emit_mapping(
                client.write_account_secrets(
                    account_id,
                    password=password,
                    refresh_token=refresh_token,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("show")
def accounts_show(
    account_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_account(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("update")
def accounts_update(
    account_id: uuid.UUID,
    row_version: Annotated[int, typer.Option(min=1)],
    lifecycle_status: str | None = None,
    group_id: uuid.UUID | None = None,
    move_group: bool = False,
    remark: str | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.update_account(
                    account_id,
                    row_version=row_version,
                    lifecycle_status=lifecycle_status,
                    group_id=group_id,
                    move_group=move_group,
                    remark=remark,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("bulk")
def accounts_bulk(
    account_id: Annotated[list[uuid.UUID], typer.Option("--account-id")],
    lifecycle_status: str | None = None,
    group_id: uuid.UUID | None = None,
    move_group: bool = False,
    add_tag_id: Annotated[list[uuid.UUID] | None, typer.Option("--add-tag-id")] = None,
    remove_tag_id: Annotated[list[uuid.UUID] | None, typer.Option("--remove-tag-id")] = None,
    forwarding_enabled: bool | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.bulk_mutate_accounts(
                    account_id,
                    lifecycle_status=lifecycle_status,
                    group_id=group_id,
                    move_group=move_group,
                    add_tag_ids=add_tag_id or [],
                    remove_tag_ids=remove_tag_id or [],
                    forwarding_enabled=forwarding_enabled,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("bulk-preview")
def accounts_bulk_preview(
    scope: Annotated[str, typer.Option(help="ids or filter")] = "ids",
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    filter_lifecycle: Annotated[str | None, typer.Option("--filter-lifecycle")] = None,
    filter_token: Annotated[str | None, typer.Option("--filter-token-status")] = None,
    filter_mail_health: Annotated[str | None, typer.Option("--filter-mail-health")] = None,
    view: Annotated[str | None, typer.Option("--view")] = None,
    saved_view_id: Annotated[uuid.UUID | None, typer.Option("--saved-view-id")] = None,
    lifecycle_status: Annotated[str | None, typer.Option("--set-lifecycle")] = None,
    group_id: Annotated[uuid.UUID | None, typer.Option("--move-group-id")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    selection: dict[str, object] = {
        "scope": scope,
        "account_ids": [str(item) for item in account_id or []],
    }
    if scope == "filter":
        selection.update(
            {
                "lifecycle_status": filter_lifecycle,
                "token_status": filter_token,
                "mail_health_status": filter_mail_health,
                "view": view,
                "saved_view_id": str(saved_view_id) if saved_view_id else None,
            }
        )
    changes = {
        "lifecycle_status": lifecycle_status,
        "move_group": group_id is not None,
        "group_id": str(group_id) if group_id else None,
    }
    try:
        with _client() as client:
            emit_mapping(
                client.preview_bulk_accounts(selection=selection, changes=changes),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("bulk-execute")
def accounts_bulk_execute(
    preview_token: Annotated[
        str,
        typer.Option("--preview-token", envvar="SEM_BULK_PREVIEW_TOKEN"),
    ],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.execute_bulk_preview(preview_token), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("tags")
def accounts_tags(
    account_id: uuid.UUID,
    tag_id: Annotated[list[uuid.UUID] | None, typer.Option("--tag-id")] = None,
    action: Annotated[str, typer.Option(help="add, remove or replace")] = "replace",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            result = (
                client.mutate_account_tags(account_id, action=action, tag_ids=tag_id)
                if tag_id is not None
                else client.list_account_tags(account_id)
            )
            emit_mapping(result, output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("archive")
def accounts_archive(
    account_id: uuid.UUID,
    row_version: Annotated[int, typer.Option(min=1)],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.archive_account(account_id, row_version), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("purge")
def accounts_purge(
    account_id: uuid.UUID,
    confirm_email: str,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm permanent account deletion")] = False,
) -> None:
    if not yes and not typer.confirm(f"Permanently delete {confirm_email} and all related data?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.purge_account(account_id, confirm_email)
        typer.echo(str(account_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@accounts_app.command("aliases")
def accounts_aliases(
    account_id: uuid.UUID,
    alias: Annotated[list[str] | None, typer.Option("--alias")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            data = (
                client.replace_aliases(account_id, alias)
                if alias is not None
                else client.list_aliases(account_id)
            )
            emit_mapping(data, output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@health_app.command("check")
def health_check(
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
    mode: Annotated[str, typer.Option(help="metadata or connectivity")] = "metadata",
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_health_check(
                    account_id or [],
                    limit=limit,
                    mode=mode,
                    idempotency_key=idempotency_key,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@refresh_app.command("start")
def refresh_start(
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    failed_only: Annotated[bool, typer.Option("--failed-only")] = False,
    limit: Annotated[int, typer.Option(min=1, max=5_000)] = 500,
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_token_refresh(
                    account_id or [],
                    failed_only=failed_only,
                    limit=limit,
                    idempotency_key=idempotency_key,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@refresh_app.command("logs")
def refresh_logs(
    account_id: uuid.UUID | None = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_token_refresh_logs(account_id=account_id, limit=limit),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@refresh_app.command("summary")
def refresh_summary(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.token_refresh_summary(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("policy")
def retention_policy(
    account_id: uuid.UUID,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    retain_bodies: Annotated[bool, typer.Option("--retain-bodies/--list-only")] = False,
    folder: Annotated[list[str] | None, typer.Option("--folder")] = None,
    max_messages: Annotated[int, typer.Option(min=1, max=100_000)] = 1000,
    max_age_days: Annotated[int, typer.Option(min=1, max=3650)] = 30,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.write_retention_policy(
                    account_id,
                    enabled=enabled,
                    retain_bodies=retain_bodies,
                    folders=folder or ["inbox"],
                    max_messages=max_messages,
                    max_age_days=max_age_days,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("policies")
def retention_policies(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_retention_policies(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("policy-show")
def retention_policy_show(
    account_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_retention_policy(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("mail")
def retention_mail(
    account_id: uuid.UUID,
    folder: str = "inbox",
    offset: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_retained_mail(
                    account_id,
                    folder=folder,
                    offset=offset,
                    limit=limit,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("mail-show")
def retention_mail_show(
    account_id: uuid.UUID,
    message_id: str,
    folder: str = "inbox",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.get_retained_mail(account_id, message_id, folder=folder),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("clear")
def retention_clear(
    account_id: uuid.UUID | None = None,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm retained cache deletion")] = False,
) -> None:
    target = str(account_id) if account_id else "all accounts"
    if not yes and not typer.confirm(f"Delete retained mail cache for {target}?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.clear_retained_mail(account_id)
        typer.echo(target)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("sync")
def retention_sync(
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    limit: Annotated[int, typer.Option(min=1, max=5000)] = 500,
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_retention_sync(
                    account_id or [],
                    limit=limit,
                    idempotency_key=idempotency_key,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@retention_app.command("stats")
def retention_stats(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.retention_stats(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("create")
def shares_create(
    account_id: uuid.UUID,
    duration_minutes: Annotated[int, typer.Option(min=1, max=2_628_000)] = 1440,
    never_expires: bool = False,
    folder: Annotated[list[str] | None, typer.Option("--folder")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_email_share(
                    account_id,
                    duration_minutes=duration_minutes,
                    never_expires=never_expires,
                    allowed_folders=folder or ["inbox"],
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("list")
def shares_list(
    account_id: uuid.UUID | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_email_shares(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("revoke")
def shares_revoke(
    share_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.revoke_email_share(share_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("delete")
def shares_delete(share_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            client.delete_email_share(share_id)
        typer.echo(str(share_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


def _public_share_token(value: str | None) -> str:
    return value or typer.prompt("Share token", hide_input=True)


@shares_app.command("public-status")
def shares_public_status(
    token: Annotated[str | None, typer.Option(envvar="SEM_SHARE_TOKEN", hide_input=True)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_public_share_status(_public_share_token(token)), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("public-mail")
def shares_public_mail(
    token: Annotated[str | None, typer.Option(envvar="SEM_SHARE_TOKEN", hide_input=True)] = None,
    folder: str = "inbox",
    source: str = "auto",
    offset: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_public_share_mail(
                    _public_share_token(token),
                    folder=folder,
                    source=source,
                    offset=offset,
                    limit=limit,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@shares_app.command("public-show")
def shares_public_show(
    message_id: str,
    token: Annotated[str | None, typer.Option(envvar="SEM_SHARE_TOKEN", hide_input=True)] = None,
    folder: str = "inbox",
    source: str = "auto",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.get_public_share_mail(
                    _public_share_token(token),
                    message_id,
                    folder=folder,
                    source=source,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("destinations")
def forwarding_destinations(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_forwarding_destinations(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("destination-create")
def forwarding_destination_create(
    name: str,
    secret: Annotated[str | None, typer.Option(envvar="SEM_FORWARDING_SECRET", hide_input=True)] = None,
    host: str = "",
    port: int = 0,
    username: str = "",
    recipient: str = "",
    from_email: str = "",
    use_ssl: bool = True,
    use_tls: bool = False,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    resolved_secret = secret or typer.prompt("Destination secret", hide_input=True)
    config: dict[str, str | int | bool] = {
        "host": host,
        "port": port or (465 if use_ssl else 587),
        "username": username,
        "recipient": recipient,
        "from_email": from_email,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
    }
    try:
        with _client() as client:
            emit_mapping(
                client.create_forwarding_destination(
                    name=name,
                    channel="smtp",
                    config=config,
                    secret=resolved_secret,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("destination-update")
def forwarding_destination_update(
    destination_id: uuid.UUID,
    name: str,
    secret: Annotated[
        str | None,
        typer.Option(envvar="SEM_FORWARDING_SECRET", hide_input=True),
    ] = None,
    host: str = "",
    port: int = 0,
    username: str = "",
    recipient: str = "",
    from_email: str = "",
    use_ssl: bool = True,
    use_tls: bool = False,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    config: dict[str, str | int | bool] = {
        "host": host,
        "port": port or (465 if use_ssl else 587),
        "username": username,
        "recipient": recipient,
        "from_email": from_email,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
    }
    try:
        with _client() as client:
            emit_mapping(
                client.update_forwarding_destination(
                    destination_id,
                    name=name,
                    config=config,
                    secret=secret,
                    enabled=enabled,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("destination-test")
def forwarding_destination_test(
    destination_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.test_forwarding_destination(destination_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("destination-delete")
def forwarding_destination_delete(
    destination_id: uuid.UUID,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm destination deletion")] = False,
) -> None:
    if not yes and not typer.confirm("Delete this forwarding destination?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.delete_forwarding_destination(destination_id)
        typer.echo(str(destination_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("account-show")
def forwarding_account_show(
    account_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_account_forwarding(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("account-set")
def forwarding_account_set(
    account_id: uuid.UUID,
    destination_id: Annotated[list[uuid.UUID] | None, typer.Option("--destination-id")] = None,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    include_junk: bool = False,
    window_minutes: Annotated[int, typer.Option(min=0, max=10_080)] = 0,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.write_account_forwarding(
                    account_id,
                    enabled=enabled,
                    include_junk=include_junk,
                    window_minutes=window_minutes,
                    destination_ids=destination_id or [],
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("run")
def forwarding_run(
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    limit: Annotated[int, typer.Option(min=1, max=5000)] = 500,
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_forwarding_job(
                    account_id or [],
                    limit=limit,
                    idempotency_key=idempotency_key,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("cursor-reset")
def forwarding_cursor_reset(
    account_id: uuid.UUID,
    cursor_at: Annotated[str | None, typer.Option("--cursor-at")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.reset_forwarding_cursor(account_id, cursor_at), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@forwarding_app.command("logs")
def forwarding_logs(
    account_id: uuid.UUID | None = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_forwarding_deliveries(account_id=account_id, limit=limit),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


def _write_schedule_command(
    *,
    schedule_id: uuid.UUID | None,
    name: str,
    cron_expression: str,
    timezone: str,
    task_type: str,
    enabled: bool,
    failed_only: bool,
    limit: int,
    account_id: list[uuid.UUID] | None,
    output: OutputFormat,
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.write_schedule(
                    schedule_id=schedule_id,
                    name=name,
                    cron_expression=cron_expression,
                    timezone=timezone,
                    task_type=task_type,
                    enabled=enabled,
                    failed_only=failed_only,
                    limit=limit,
                    account_ids=account_id or [],
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@schedules_app.command("list")
def schedules_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_schedules(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@schedules_app.command("create")
def schedules_create(
    name: str,
    cron_expression: Annotated[str, typer.Option("--cron")],
    timezone: str = "Asia/Shanghai",
    task_type: Annotated[
        str,
        typer.Option(help="token_refresh, retention_sync or forwarding"),
    ] = "token_refresh",
    enabled: bool = True,
    failed_only: bool = False,
    limit: Annotated[int, typer.Option(min=1, max=5_000)] = 500,
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    _write_schedule_command(
        schedule_id=None,
        name=name,
        cron_expression=cron_expression,
        timezone=timezone,
        task_type=task_type,
        enabled=enabled,
        failed_only=failed_only,
        limit=limit,
        account_id=account_id,
        output=output,
    )


@schedules_app.command("update")
def schedules_update(
    schedule_id: uuid.UUID,
    name: str,
    cron_expression: Annotated[str, typer.Option("--cron")],
    timezone: str = "Asia/Shanghai",
    task_type: Annotated[
        str,
        typer.Option(help="token_refresh, retention_sync or forwarding"),
    ] = "token_refresh",
    enabled: bool = True,
    failed_only: bool = False,
    limit: Annotated[int, typer.Option(min=1, max=5_000)] = 500,
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    _write_schedule_command(
        schedule_id=schedule_id,
        name=name,
        cron_expression=cron_expression,
        timezone=timezone,
        task_type=task_type,
        enabled=enabled,
        failed_only=failed_only,
        limit=limit,
        account_id=account_id,
        output=output,
    )


@schedules_app.command("delete")
def schedules_delete(schedule_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            client.delete_schedule(schedule_id)
        typer.echo(str(schedule_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@imports_app.command("plan")
def imports_plan(
    source: Path,
    group_id: uuid.UUID | None = None,
    remark: str = "",
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    if not source.is_file():
        typer.echo(f"Import source does not exist: {source}", err=True)
        raise typer.Exit(code=2)
    try:
        with _client() as client:
            emit_mapping(
                client.create_import_batch(
                    content=source.read_text(encoding="utf-8"),
                    account_type="outlook",
                    provider="outlook",
                    group_id=group_id,
                    remark=remark,
                    idempotency_key=idempotency_key,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@imports_app.command("list")
def imports_list(
    limit: Annotated[int, typer.Option(min=1, max=200)] = 50,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_import_batches(limit), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@imports_app.command("show")
def imports_show(
    batch_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_import_batch(batch_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@imports_app.command("commit")
def imports_commit(
    batch_id: uuid.UUID,
    connectivity_check: Annotated[
        bool,
        typer.Option("--connectivity-check/--no-connectivity-check"),
    ] = True,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            batch = client.commit_import_batch(batch_id)
            created_ids = [
                uuid.UUID(str(item["created_account_id"]))
                for item in batch.get("items", [])
                if item.get("created_account_id")
            ]
            health_job = (
                client.create_health_check(
                    created_ids,
                    limit=max(1, len(created_ids)),
                    mode="connectivity",
                )
                if connectivity_check and created_ids
                else None
            )
            emit_mapping(
                {
                    "batch": batch,
                    "connectivity_job": health_job,
                },
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@imports_app.command("rollback")
def imports_rollback(
    batch_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.rollback_import_batch(batch_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)



@mail_app.command("list")
def mail_list(
    account_id: uuid.UUID,
    folder: str = "inbox",
    method: str = "auto",
    offset: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_mail(
                    account_id,
                    folder=folder,
                    method=method,
                    offset=offset,
                    limit=limit,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@mail_app.command("show")
def mail_show(
    account_id: uuid.UUID,
    message_id: str,
    folder: str = "inbox",
    method: str = "auto",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.get_mail(
                    account_id,
                    message_id,
                    folder=folder,
                    method=method,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@codes_app.command("latest")
def codes_latest(
    account_id: uuid.UUID,
    recent_minutes: Annotated[int, typer.Option(min=1, max=1_440)] = 30,
    messages_per_account: Annotated[int, typer.Option(min=1, max=100)] = 30,
    include_junk: Annotated[bool, typer.Option("--junk/--no-junk")] = True,
    method: str = "auto",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_verification_codes(
                    account_id,
                    recent_minutes=recent_minutes,
                    messages_per_account=messages_per_account,
                    include_junk=include_junk,
                    method=method,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@codes_app.command("query")
def codes_query(
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    recent_minutes: Annotated[int, typer.Option(min=1, max=1_440)] = 30,
    messages_per_account: Annotated[int, typer.Option(min=1, max=100)] = 30,
    account_limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
    include_junk: Annotated[bool, typer.Option("--junk/--no-junk")] = True,
    method: str = "auto",
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.query_verification_codes(
                    account_ids=account_id or [],
                    recent_minutes=recent_minutes,
                    messages_per_account=messages_per_account,
                    account_limit=account_limit,
                    include_junk=include_junk,
                    method=method,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@mail_app.command("raw")
def mail_raw(
    account_id: uuid.UUID,
    message_id: str,
    output_file: Annotated[Path, typer.Option("--output-file", "-O")],
    folder: str = "inbox",
    method: str = "auto",
) -> None:
    try:
        with _client() as client:
            output_file.write_bytes(
                client.download_mail_resource(
                    account_id,
                    message_id,
                    folder=folder,
                    method=method,
                )
            )
        typer.echo(str(output_file))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@mail_app.command("attachment")
def mail_attachment(
    account_id: uuid.UUID,
    message_id: str,
    attachment_id: str,
    output_file: Annotated[Path, typer.Option("--output-file", "-O")],
    folder: str = "inbox",
    method: str = "auto",
) -> None:
    try:
        with _client() as client:
            output_file.write_bytes(
                client.download_mail_resource(
                    account_id,
                    message_id,
                    folder=folder,
                    method=method,
                    attachment_id=attachment_id,
                )
            )
        typer.echo(str(output_file))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@mail_app.command("read")
def mail_read(
    account_id: uuid.UUID,
    message_id: str,
    folder: str = "inbox",
    method: str = "auto",
) -> None:
    try:
        with _client() as client:
            client.mark_mail_read(account_id, message_id, folder=folder, method=method)
        typer.echo(message_id)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@mail_app.command("delete")
def mail_delete(
    account_id: uuid.UUID,
    message_id: str,
    folder: str = "inbox",
    method: str = "auto",
    yes: Annotated[bool, typer.Option("--yes", help="Confirm permanent deletion")] = False,
) -> None:
    if not yes and not typer.confirm("Permanently delete this message?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.delete_mail(account_id, message_id, folder=folder, method=method)
        typer.echo(message_id)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("list")
def proxies_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_proxy_profiles(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("create")
def proxies_create(
    name: str,
    primary_url: Annotated[
        str | None,
        typer.Option("--primary-url", envvar="SEM_PROXY_URL", help="Prefer env or hidden prompt"),
    ] = None,
    fallback_url_1: str | None = None,
    fallback_url_2: str | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    resolved_primary = primary_url or typer.prompt("Primary proxy URL", hide_input=True)
    try:
        with _client() as client:
            emit_mapping(
                client.create_proxy_profile(
                    name=name,
                    primary_url=resolved_primary,
                    fallback_url_1=fallback_url_1,
                    fallback_url_2=fallback_url_2,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("update")
def proxies_update(
    profile_id: uuid.UUID,
    name: str,
    primary_url: Annotated[
        str | None,
        typer.Option("--primary-url", envvar="SEM_PROXY_URL", help="Prefer env or hidden prompt"),
    ] = None,
    fallback_url_1: str | None = None,
    fallback_url_2: str | None = None,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    resolved_primary = primary_url or typer.prompt("Primary proxy URL", hide_input=True)
    try:
        with _client() as client:
            emit_mapping(
                client.update_proxy_profile(
                    profile_id,
                    name=name,
                    primary_url=resolved_primary,
                    fallback_url_1=fallback_url_1,
                    fallback_url_2=fallback_url_2,
                    enabled=enabled,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("delete")
def proxies_delete(
    profile_id: uuid.UUID,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm proxy profile deletion")] = False,
) -> None:
    if not yes and not typer.confirm("Delete this proxy profile?"):
        raise typer.Abort()
    try:
        with _client() as client:
            client.delete_proxy_profile(profile_id)
        typer.echo(str(profile_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("assign-account")
def proxies_assign_account(
    account_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
) -> None:
    try:
        with _client() as client:
            client.assign_proxy("accounts", account_id, profile_id)
        typer.echo(str(account_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("assign-group")
def proxies_assign_group(
    group_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
) -> None:
    try:
        with _client() as client:
            client.assign_proxy("groups", group_id, profile_id)
        typer.echo(str(group_id))
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("resolve")
def proxies_resolve(
    account_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.resolve_proxy(account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)



@security_app.command("rotate-key")
def security_rotate_key(
    old_key_version: Annotated[int, typer.Option(min=1)],
    old_master_key: Annotated[str | None, typer.Option(envvar="SEM_OLD_MASTER_KEY", hide_input=True)] = None,
    commit: Annotated[
        bool,
        typer.Option("--commit", help="Apply rotation; default is a read-only inventory"),
    ] = False,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    resolved_key = old_master_key or typer.prompt("Old master key", hide_input=True)
    try:
        with _client() as client:
            emit_mapping(
                client.rotate_master_key(
                    old_master_key=resolved_key,
                    old_key_version=old_key_version,
                    commit=commit,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("list")
def projects_list(
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_projects(), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("create")
def projects_create(
    name: str,
    account_id: Annotated[list[uuid.UUID] | None, typer.Option("--account-id")] = None,
    description: str = "",
    lease_seconds: Annotated[int, typer.Option(min=30, max=3600)] = 300,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.create_project(
                    name=name,
                    description=description,
                    lease_seconds=lease_seconds,
                    account_ids=account_id or [],
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("accounts")
def projects_accounts(
    project_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_project_accounts(project_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("accounts-add")
def projects_accounts_add(
    project_id: uuid.UUID,
    account_id: Annotated[list[uuid.UUID], typer.Option("--account-id")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.add_project_accounts(project_id, account_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("status")
def projects_status(
    project_id: uuid.UUID,
    status: Annotated[str, typer.Option(help="active, paused or completed")],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.set_project_status(project_id, status), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("events")
def projects_events(
    project_id: uuid.UUID,
    after: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 200,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_project_events(project_id, after=after, limit=limit),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("account-action")
def projects_account_action(
    project_id: uuid.UUID,
    action: Annotated[str, typer.Option(help="reset_failed, remove or restore")],
    project_account_id: Annotated[
        list[uuid.UUID],
        typer.Option("--project-account-id"),
    ],
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.mutate_project_accounts(
                    project_id,
                    action=action,
                    project_account_ids=project_account_id,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("claim")
def projects_claim(
    project_id: uuid.UUID,
    owner: str,
    lease_seconds: Annotated[int | None, typer.Option(min=30, max=3600)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.claim_project(
                    project_id,
                    owner=owner,
                    lease_seconds=lease_seconds,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


def _project_action_command(
    *,
    project_account_id: uuid.UUID,
    action: str,
    claim_token: str | None,
    error_summary: str | None,
    output: OutputFormat,
) -> None:
    resolved_token = claim_token or typer.prompt("Claim token", hide_input=True)
    try:
        with _client() as client:
            emit_mapping(
                client.project_lease_action(
                    project_account_id,
                    action=action,
                    claim_token=resolved_token,
                    error_summary=error_summary,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("complete")
def projects_complete(
    project_account_id: uuid.UUID,
    claim_token: Annotated[str | None, typer.Option(envvar="SEM_CLAIM_TOKEN", hide_input=True)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    _project_action_command(
        project_account_id=project_account_id,
        action="complete",
        claim_token=claim_token,
        error_summary=None,
        output=output,
    )


@projects_app.command("heartbeat")
def projects_heartbeat(
    project_account_id: uuid.UUID,
    claim_token: Annotated[
        str | None,
        typer.Option(envvar="SEM_CLAIM_TOKEN", hide_input=True),
    ] = None,
    lease_seconds: Annotated[int | None, typer.Option(min=30, max=3600)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    resolved_token = claim_token or typer.prompt("Claim token", hide_input=True)
    try:
        with _client() as client:
            emit_mapping(
                client.heartbeat_project_lease(
                    project_account_id,
                    claim_token=resolved_token,
                    lease_seconds=lease_seconds,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@projects_app.command("fail")
def projects_fail(
    project_account_id: uuid.UUID,
    error_summary: str,
    claim_token: Annotated[str | None, typer.Option(envvar="SEM_CLAIM_TOKEN", hide_input=True)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    _project_action_command(
        project_account_id=project_account_id,
        action="fail",
        claim_token=claim_token,
        error_summary=error_summary,
        output=output,
    )


@projects_app.command("release")
def projects_release(
    project_account_id: uuid.UUID,
    claim_token: Annotated[str | None, typer.Option(envvar="SEM_CLAIM_TOKEN", hide_input=True)] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    _project_action_command(
        project_account_id=project_account_id,
        action="release",
        claim_token=claim_token,
        error_summary=None,
        output=output,
    )


@jobs_app.command("show")
def job_show(
    job_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "table",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.get_job(job_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@jobs_app.command("list")
def jobs_list(
    limit: Annotated[int, typer.Option(min=1, max=200)] = 50,
    status: str | None = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.list_jobs(limit, status), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@jobs_app.command("watch")
def job_watch(job_id: uuid.UUID) -> None:
    try:
        with _client() as client:
            for event in client.watch_job(job_id):
                emit_json(event)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@jobs_app.command("pause")
def job_pause(
    job_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.pause_job(job_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@jobs_app.command("resume")
def job_resume(
    job_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.resume_job(job_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@jobs_app.command("cancel")
def job_cancel(
    job_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.cancel_job(job_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@proxies_app.command("probe")
def proxies_probe(
    profile_id: uuid.UUID,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(client.probe_proxy(profile_id), output)
    except httpx.HTTPError as exc:
        _handle_http_error(exc)


@audit_app.command("list")
def audit_list(
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 200,
    output: Annotated[OutputFormat, typer.Option("--output", "-o")] = "json",
) -> None:
    try:
        with _client() as client:
            emit_mapping(
                client.list_audit_logs(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    limit=limit,
                ),
                output,
            )
    except httpx.HTTPError as exc:
        _handle_http_error(exc)
