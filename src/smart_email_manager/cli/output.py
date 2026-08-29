from __future__ import annotations

import json
from typing import Any, Literal

from rich.console import Console
from rich.table import Table

OutputFormat = Literal["table", "json", "jsonl"]
stdout = Console(stderr=False)


def emit_json(data: Any) -> None:
    stdout.print_json(json.dumps(data, default=str, ensure_ascii=False))


def emit_jsonl(items: list[dict[str, Any]]) -> None:
    for item in items:
        stdout.print(json.dumps(item, default=str, ensure_ascii=False), markup=False)


def emit_mapping(data: dict[str, Any], output: OutputFormat) -> None:
    if output in {"json", "jsonl"}:
        emit_json(data)
        return
    table = Table(show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        table.add_row(key, str(value))
    stdout.print(table)


def emit_accounts(data: dict[str, Any], output: OutputFormat) -> None:
    items = list(data.get("items", []))
    if output == "json":
        emit_json(data)
        return
    if output == "jsonl":
        emit_jsonl(items)
        return
    table = Table("ID", "Email", "Lifecycle", "Token", "Mail health", "Reason")
    for item in items:
        table.add_row(
            str(item.get("id", "")),
            str(item.get("email", "")),
            str(item.get("lifecycle_status", "")),
            str(item.get("token_status", "")),
            str(item.get("mail_health_status", "")),
            str(item.get("health_reason_code") or "-"),
        )
    stdout.print(table)
    if data.get("next_cursor"):
        stdout.print(f"next_cursor={data['next_cursor']}", style="dim")
