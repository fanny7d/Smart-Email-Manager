from __future__ import annotations

import asyncio
import html
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.codes import VerificationCodePage, VerificationCodeRead
from smart_email_manager.db.models import Account
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.services.mail import get_mail_detail, list_mail

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_KEYWORD_RE = re.compile(
    r"verification\s*code|security\s*code|login\s*code|one[-\s]*time(?:\s+password|\s+code)?|"
    r"passcode|auth(?:entication)?\s*code|otp|code|验证码|校验码|动态码|安全码|一次性密码|登录码",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"(?<![A-Z0-9])(?:\d(?:[\s-]?\d){3,7}|[A-Z0-9]{4,10})(?![A-Z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedCode:
    code: str
    code_type: str
    confidence: str
    score: int


def _plain_text(value: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html.unescape(value or ""))).strip()


def _code_type(context: str) -> str:
    lowered = context.lower()
    if "otp" in lowered or "one-time" in lowered or "一次性密码" in context:
        return "otp"
    if "login" in lowered or "登录码" in context:
        return "login"
    if "security" in lowered or "安全码" in context:
        return "security"
    return "verification"


def _normalize_candidate(value: str) -> str:
    return re.sub(r"[\s-]", "", value).upper()


def _valid_candidate(value: str) -> bool:
    if not 4 <= len(value) <= 10:
        return False
    if not any(character.isdigit() for character in value):
        return False
    return not (value.isdigit() and not 4 <= len(value) <= 8)


def extract_verification_code(subject: str, body: str) -> ExtractedCode | None:
    """Extract one context-bound code, preferring subject and phrase proximity."""
    candidates: list[ExtractedCode] = []
    for source_rank, text in ((40, _plain_text(subject)), (20, _plain_text(body))):
        for keyword in _KEYWORD_RE.finditer(text):
            window_start = max(0, keyword.start() - 24)
            window_end = min(len(text), keyword.end() + 64)
            context = text[window_start:window_end]
            for match in _CODE_RE.finditer(context):
                code = _normalize_candidate(match.group(0))
                if not _valid_candidate(code):
                    continue
                absolute_start = window_start + match.start()
                distance = min(abs(absolute_start - keyword.start()), abs(absolute_start - keyword.end()))
                phrase_bonus = 30 if distance <= 16 else 10
                digit_bonus = 5 if code.isdigit() else 0
                candidates.append(
                    ExtractedCode(
                        code=code,
                        code_type=_code_type(context),
                        confidence="high" if source_rank == 40 or distance <= 16 else "medium",
                        score=source_rank + phrase_bonus + digit_bonus - min(distance, 30),
                    )
                )
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.score)


def _parse_received_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def find_account_verification_codes(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    recent_minutes: int,
    messages_per_account: int,
    include_junk: bool,
    method: str,
) -> VerificationCodePage:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    cutoff = datetime.now(UTC) - timedelta(minutes=recent_minutes)
    page = await list_mail(
        session,
        account_id,
        folder="all" if include_junk else "inbox",
        offset=0,
        limit=messages_per_account,
        method=method,
    )
    codes: list[VerificationCodeRead] = []
    for message in page.items:
        received_at = _parse_received_at(message.received_at)
        if received_at is not None and received_at < cutoff:
            continue
        preview_result = extract_verification_code(message.subject, message.body_preview)
        if preview_result is None and not _KEYWORD_RE.search(
            f"{message.subject} {message.body_preview}"
        ):
            continue
        extracted = preview_result
        selected_method = page.method
        if extracted is None:
            detail = await get_mail_detail(
                session,
                account_id,
                folder=message.folder,
                message_id=message.id,
                method=method,
            )
            extracted = extract_verification_code(detail.subject, detail.body)
            selected_method = detail.method
        if extracted is None:
            continue
        codes.append(
            VerificationCodeRead(
                account_id=account.id,
                email=account.email,
                code=extracted.code,
                code_type=extracted.code_type,
                subject=message.subject,
                sender=message.sender,
                received_at=message.received_at,
                folder=message.folder,
                message_id=message.id,
                method=selected_method,
                confidence=extracted.confidence,
            )
        )
    codes.sort(key=lambda item: item.received_at, reverse=True)
    return VerificationCodePage(items=codes, checked_accounts=1)


async def _scan_one_account(
    account_id: uuid.UUID,
    *,
    recent_minutes: int,
    messages_per_account: int,
    include_junk: bool,
    method: str,
    semaphore: asyncio.Semaphore,
) -> VerificationCodePage:
    async with semaphore, get_session_factory()() as session:
        return await find_account_verification_codes(
            session,
            account_id,
            recent_minutes=recent_minutes,
            messages_per_account=messages_per_account,
            include_junk=include_junk,
            method=method,
        )


async def find_fleet_verification_codes(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    recent_minutes: int,
    messages_per_account: int,
    account_limit: int,
    include_junk: bool,
    method: str,
) -> VerificationCodePage:
    query = select(Account.id, Account.authorization_status).where(
        Account.account_type == "outlook",
        Account.lifecycle_status == "active",
    )
    if account_ids:
        query = query.where(Account.id.in_(account_ids))
    query = query.order_by(Account.email).limit(account_limit)
    selected_rows = list((await session.execute(query)).all())
    selected_ids = [row.id for row in selected_rows]
    if not selected_ids:
        return VerificationCodePage(items=[], checked_accounts=0)

    errors: dict[str, str] = {}
    if account_ids:
        selected_set = set(selected_ids)
        for account_id in account_ids:
            if account_id not in selected_set:
                errors[str(account_id)] = "ACCOUNT_NOT_ACTIVE_OR_NOT_FOUND"
    scan_ids: list[uuid.UUID] = []
    for row in selected_rows:
        if row.authorization_status in {"invalid", "reauthorization_required"}:
            errors[str(row.id)] = "ACCOUNT_AUTHORIZATION_INVALID"
        else:
            scan_ids.append(row.id)

    semaphore = asyncio.Semaphore(10)
    results = await asyncio.gather(
        *(
            asyncio.wait_for(
                _scan_one_account(
                    account_id,
                    recent_minutes=recent_minutes,
                    messages_per_account=messages_per_account,
                    include_junk=include_junk,
                    method=method,
                    semaphore=semaphore,
                ),
                timeout=45,
            )
            for account_id in scan_ids
        ),
        return_exceptions=True,
    )
    items: list[VerificationCodeRead] = []
    for account_id, result in zip(scan_ids, results, strict=True):
        if isinstance(result, BaseException):
            errors[str(account_id)] = (
                "ACCOUNT_SCAN_TIMEOUT" if isinstance(result, TimeoutError) else str(result)
            )
        else:
            items.extend(result.items)
    items.sort(key=lambda item: item.received_at, reverse=True)
    return VerificationCodePage(
        items=items,
        checked_accounts=len(selected_ids),
        failed_accounts=len(errors),
        partial_errors=errors,
    )
