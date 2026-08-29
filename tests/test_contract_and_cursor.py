from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from smart_email_manager.api.app import app
from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.services.accounts import (
    AccountCursor,
    decode_account_cursor,
    encode_account_cursor,
)


def test_account_cursor_round_trip() -> None:
    cursor = AccountCursor(datetime(2026, 8, 28, tzinfo=UTC), uuid.uuid4())
    assert decode_account_cursor(encode_account_cursor(cursor)) == cursor


def test_invalid_account_cursor_is_typed_problem() -> None:
    with pytest.raises(ApiProblem) as error:
        decode_account_cursor("not-a-cursor")
    assert error.value.problem.code == "INVALID_CURSOR"


def test_openapi_operation_ids_are_explicit_and_unique() -> None:
    operation_ids: list[str] = []
    for path in app.openapi()["paths"].values():
        for operation in path.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation_ids.append(operation["operationId"])
    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    assert all("_api_v1_" not in operation_id for operation_id in operation_ids)
