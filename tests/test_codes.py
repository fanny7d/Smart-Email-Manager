from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead, MailSummaryRead
from smart_email_manager.services import codes as codes_service
from smart_email_manager.services.codes import _parse_received_at, extract_verification_code


@pytest.mark.parametrize(
    ("subject", "body", "expected", "code_type"),
    [
        ("Your verification code is 483921", "Expires in 10 minutes", "483921", "verification"),
        ("登录验证码： 12 34 56", "请勿告诉任何人", "123456", "verification"),
        ("One-time password", "Use OTP 8K4Q2X to continue", "8K4Q2X", "otp"),
        ("Security code: 9027", "Microsoft account team", "9027", "security"),
    ],
)
def test_extract_verification_code(
    subject: str,
    body: str,
    expected: str,
    code_type: str,
) -> None:
    result = extract_verification_code(subject, body)
    assert result is not None
    assert result.code == expected
    assert result.code_type == code_type


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        ("Order 483921 shipped", "Track your package"),
        ("Monthly report 2026", "No authentication requested"),
        ("Welcome", "Thanks for signing up"),
    ],
)
def test_extract_verification_code_rejects_unrelated_numbers(subject: str, body: str) -> None:
    assert extract_verification_code(subject, body) is None


def test_imap_rfc2822_received_at_is_parsed_for_recent_window() -> None:
    parsed = _parse_received_at("Sat, 29 Aug 2026 02:11:17 +0000")
    assert parsed == datetime(2026, 8, 29, 2, 11, 17, tzinfo=UTC)


async def test_verification_code_api_single_and_fleet(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = await api_client.post(
        "/api/v1/accounts",
        json={"email": "codes-one@outlook.com", "provider": "outlook"},
    )
    second = await api_client.post(
        "/api/v1/accounts",
        json={"email": "codes-two@outlook.com", "provider": "outlook"},
    )
    now = datetime.now(UTC).isoformat()

    async def fake_list(*_args: object, **_kwargs: object) -> MailPageRead:
        return MailPageRead(
            items=[
                MailSummaryRead(
                    id="verification-message",
                    folder="junkemail",
                    subject="Your verification code",
                    sender="security@example.com",
                    recipients=[],
                    received_at=now,
                    is_read=False,
                    has_attachments=False,
                    body_preview="Use code 654321 to continue",
                    id_mode="imap_uid",
                )
            ],
            has_more=False,
            method="imap",
        )

    async def fake_detail(*_args: object, **_kwargs: object) -> MailDetailRead:
        return MailDetailRead(
            id="verification-message",
            folder="junkemail",
            subject="Your verification code",
            sender="security@example.com",
            recipients=[],
            cc=[],
            received_at=now,
            is_read=False,
            body="Your verification code is 654321. It expires in 10 minutes.",
            body_type="text",
            attachments=[],
            id_mode="imap_uid",
            method="imap",
        )

    monkeypatch.setattr(codes_service, "list_mail", fake_list)
    monkeypatch.setattr(codes_service, "get_mail_detail", fake_detail)

    single = await api_client.get(
        f"/api/v1/accounts/{first.json()['id']}/verification-codes"
    )
    assert single.status_code == 200
    assert single.json()["items"][0]["code"] == "654321"
    assert single.json()["items"][0]["folder"] == "junkemail"

    fleet = await api_client.post(
        "/api/v1/verification-codes/query",
        json={"account_ids": [first.json()["id"], second.json()["id"]]},
    )
    assert fleet.status_code == 200
    assert fleet.json()["checked_accounts"] == 2
    assert fleet.json()["failed_accounts"] == 0
    assert {item["email"] for item in fleet.json()["items"]} == {
        "codes-one@outlook.com",
        "codes-two@outlook.com",
    }
