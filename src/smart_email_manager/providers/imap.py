from __future__ import annotations

import asyncio
import email
import imaplib
import re
import socket
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from email.header import decode_header
from email.message import Message
from email.policy import default
from email.utils import getaddresses
from typing import Any, cast
from urllib.parse import unquote, urlparse

import httpx
import socks

from smart_email_manager.providers.base import (
    DownloadedAttachment,
    MailAttachment,
    MailMessageDetail,
    MailMessageSummary,
    MailPage,
    ProviderAccount,
    ProviderHealthResult,
    ProviderOperationError,
    TokenRefreshResult,
)
from smart_email_manager.providers.graph import GRAPH_TOKEN_URL
from smart_email_manager.services.secrets import DecryptedAccountSecrets

FOLDER_CANDIDATES = {
    "inbox": ["INBOX"],
    "junkemail": ["Junk Email", "Junk", "Spam", "[Gmail]/Spam"],
    "deleteditems": ["Deleted Items", "Deleted", "Trash", "[Gmail]/Trash"],
}
PROXY_SOCKET_LOCK = threading.RLock()


@dataclass(frozen=True)
class ImapCredentials:
    host: str
    port: int
    email: str
    access_token: str | None = None
    proxy_url: str | None = None


class ImapProvider:
    channel = "imap"

    def __init__(
        self,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory

    async def _credentials(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ImapCredentials:
        proxy_url = next((value for value in account.proxy_urls if value != "direct"), None)
        host = str(account.provider_metadata.get("imap_host") or "").strip()
        if not host:
            host = "outlook.live.com"
        port = int(account.provider_metadata.get("imap_port") or 993)
        client_id = str(account.provider_metadata.get("client_id") or "").strip()
        if not client_id or not secrets.refresh_token:
            raise ProviderOperationError(
                code="IMAP_OAUTH_CREDENTIALS_MISSING",
                message="client_id or refresh_token is missing",
                status=422,
            )
        access_token = await self._get_imap_access_token(
            client_id,
            secrets.refresh_token,
            proxy_url,
        )
        if not access_token:
            raise ProviderOperationError(
                code="IMAP_OAUTH_TOKEN_REJECTED",
                message="Microsoft did not return an IMAP access token",
                status=401,
            )
        return ImapCredentials(
            host,
            port,
            account.email,
            access_token=access_token,
            proxy_url=proxy_url,
        )

    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        try:
            credentials = await self._credentials(account, secrets)
            await asyncio.to_thread(self._check_sync, credentials)
            return ProviderHealthResult(
                status="healthy",
                channel=self.channel,
                reason_code="IMAP_OK",
                details={"imap_host": credentials.host, "imap_port": credentials.port},
            )
        except ProviderOperationError as exc:
            return ProviderHealthResult(
                status="failed",
                channel=self.channel,
                reason_code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
        except (OSError, imaplib.IMAP4.error, httpx.HTTPError) as exc:
            failure = _imap_failure("IMAP_CONNECT_FAILED", exc)
            return ProviderHealthResult(
                status="failed",
                channel=self.channel,
                reason_code=failure.code,
                message=failure.message,
                retryable=failure.retryable,
                details=failure.details,
            )

    async def list_messages(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        offset: int,
        limit: int,
    ) -> MailPage:
        credentials = await self._credentials(account, secrets)
        try:
            items, has_more = await asyncio.to_thread(
                self._list_sync,
                credentials,
                account.provider_metadata,
                folder,
                offset,
                limit,
            )
            return MailPage(items=items, has_more=has_more, method=self.channel)
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            raise _imap_failure("IMAP_MAIL_LIST_FAILED", exc) from exc

    async def get_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> MailMessageDetail:
        credentials = await self._credentials(account, secrets)
        try:
            raw, is_read = await asyncio.to_thread(
                self._raw_with_flags_sync,
                credentials,
                account.provider_metadata,
                folder,
                message_id,
            )
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            raise _imap_failure("IMAP_MAIL_DETAIL_FAILED", exc) from exc
        return replace(
            parse_message_detail(raw, message_id=message_id, folder=folder),
            is_read=is_read,
        )

    async def get_raw_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> bytes:
        credentials = await self._credentials(account, secrets)
        try:
            return await asyncio.to_thread(
                self._raw_sync,
                credentials,
                account.provider_metadata,
                folder,
                message_id,
            )
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            raise _imap_failure("IMAP_MAIL_DETAIL_FAILED", exc) from exc

    async def download_attachment(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
        attachment_id: str,
    ) -> DownloadedAttachment:
        raw = await self.get_raw_message(
            account,
            secrets,
            folder=folder,
            message_id=message_id,
        )
        parts = attachment_parts(email.message_from_bytes(raw, policy=default))
        try:
            part = parts[int(attachment_id) - 1]
        except (ValueError, IndexError) as exc:
            raise ProviderOperationError(
                code="ATTACHMENT_NOT_FOUND",
                message="The requested attachment does not exist.",
                status=404,
            ) from exc
        content = decoded_payload(part)
        return DownloadedAttachment(
            name=decode_header_text(part.get_filename() or "attachment"),
            content_type=part.get_content_type(),
            content=content,
        )

    async def mark_read(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None:
        credentials = await self._credentials(account, secrets)
        try:
            await asyncio.to_thread(
                self._store_sync,
                credentials,
                account.provider_metadata,
                folder,
                message_id,
                "+FLAGS.SILENT",
                "(\\Seen)",
                False,
            )
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            raise _imap_failure("IMAP_MARK_READ_FAILED", exc) from exc

    async def delete_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None:
        credentials = await self._credentials(account, secrets)
        try:
            await asyncio.to_thread(
                self._store_sync,
                credentials,
                account.provider_metadata,
                folder,
                message_id,
                "+FLAGS.SILENT",
                "(\\Deleted)",
                True,
            )
        except (OSError, imaplib.IMAP4.error, ValueError) as exc:
            raise _imap_failure("IMAP_DELETE_FAILED", exc) from exc

    async def _get_imap_access_token(
        self,
        client_id: str,
        refresh_token: str,
        proxy_url: str | None,
    ) -> str | None:
        payload = await self._imap_token_payload(client_id, refresh_token, proxy_url)
        return str(payload.get("access_token") or "") or None

    async def _imap_token_payload(
        self,
        client_id: str,
        refresh_token: str,
        proxy_url: str | None,
    ) -> dict[str, Any]:
        client = (
            self._client_factory()
            if self._client_factory
            else httpx.AsyncClient(
                timeout=30,
                proxy=proxy_url,
                trust_env=proxy_url is None,
            )
        )
        async with client:
            response = await client.post(
                GRAPH_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
                },
            )
            if response.status_code != 200:
                raise ProviderOperationError(
                    code="IMAP_OAUTH_TOKEN_REJECTED",
                    message=f"Microsoft token endpoint returned HTTP {response.status_code}",
                    status=response.status_code if response.status_code < 500 else 502,
                    retryable=response.status_code >= 500 or response.status_code == 429,
                )
            payload = response.json()
            return payload if isinstance(payload, dict) else {}

    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        client_id = str(account.provider_metadata.get("client_id") or "").strip()
        if not client_id or not secrets.refresh_token:
            return TokenRefreshResult(
                False,
                self.channel,
                "IMAP_OAUTH_CREDENTIALS_MISSING",
                message="client_id or refresh_token is missing",
            )
        proxy_url = next((value for value in account.proxy_urls if value != "direct"), None)
        try:
            payload = await self._imap_token_payload(client_id, secrets.refresh_token, proxy_url)
            if not payload.get("access_token"):
                return TokenRefreshResult(False, self.channel, "IMAP_OAUTH_TOKEN_MISSING")
            return TokenRefreshResult(
                True,
                self.channel,
                "IMAP_OAUTH_TOKEN_REFRESHED",
                rotated_refresh_token=str(payload.get("refresh_token") or "") or None,
                details={"expires_in": int(payload.get("expires_in") or 0)},
            )
        except ProviderOperationError as exc:
            return TokenRefreshResult(
                False,
                self.channel,
                exc.code,
                message=exc.message,
                retryable=exc.retryable,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return TokenRefreshResult(
                False,
                self.channel,
                "IMAP_OAUTH_NETWORK_FAILED",
                message=str(exc)[:300],
                retryable=True,
            )

    @classmethod
    def _connect_sync(cls, credentials: ImapCredentials) -> imaplib.IMAP4_SSL:
        client = cls._open_client(credentials)
        try:
            if credentials.access_token:
                auth = (
                    f"user={credentials.email}\x01auth=Bearer {credentials.access_token}\x01\x01"
                ).encode()
                client.authenticate("XOAUTH2", lambda _challenge: auth)
            else:
                raise imaplib.IMAP4.error("No IMAP credential is available")
            return client
        except Exception:
            with suppress(Exception):
                client.logout()
            raise

    @staticmethod
    def _open_client(credentials: ImapCredentials) -> imaplib.IMAP4_SSL:
        if not credentials.proxy_url:
            return imaplib.IMAP4_SSL(credentials.host, credentials.port, timeout=30)
        parsed = urlparse(credentials.proxy_url)
        if parsed.scheme.lower() not in {"socks5", "socks5h"} or not parsed.hostname:
            raise ProviderOperationError(
                code="IMAP_PROXY_UNSUPPORTED",
                message="Raw IMAP connections require socks5:// or socks5h:// proxies.",
                status=422,
            )
        with PROXY_SOCKET_LOCK:
            original_socket = socket.socket
            try:
                socks.set_default_proxy(
                    socks.SOCKS5,
                    parsed.hostname,
                    parsed.port,
                    rdns=parsed.scheme.lower() == "socks5h",
                    username=unquote(parsed.username) if parsed.username else None,
                    password=unquote(parsed.password) if parsed.password is not None else None,
                )
                setattr(cast(Any, socket), "socket", socks.socksocket)  # noqa: B010
                return imaplib.IMAP4_SSL(credentials.host, credentials.port, timeout=30)
            finally:
                setattr(cast(Any, socket), "socket", original_socket)  # noqa: B010
                socks.set_default_proxy()

    @classmethod
    def _check_sync(cls, credentials: ImapCredentials) -> None:
        client = cls._connect_sync(credentials)
        try:
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error("INBOX is not readable")
        finally:
            _logout(client)

    @classmethod
    def _list_sync(
        cls,
        credentials: ImapCredentials,
        metadata: dict[str, Any],
        folder: str,
        offset: int,
        limit: int,
    ) -> tuple[list[MailMessageSummary], bool]:
        client = cls._connect_sync(credentials)
        try:
            _select_folder(client, metadata, folder, readonly=True)
            status, data = client.uid("search", None, "ALL")  # type: ignore[arg-type]
            if status != "OK" or not data:
                raise imaplib.IMAP4.error("UID search failed")
            uids = data[0].split()
            selected = list(reversed(uids))[offset : offset + limit]
            items: list[MailMessageSummary] = []
            for uid in selected:
                fetch_status, fetch_data = client.uid(
                    "fetch",
                    uid,
                    "(RFC822.HEADER FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[TEXT]<0.1024>)",
                )
                if fetch_status != "OK" or not fetch_data:
                    continue
                payload, metadata_bytes = _fetch_payload(fetch_data)
                message = email.message_from_bytes(payload, policy=default)
                preview = _body_preview(payload)
                items.append(
                    MailMessageSummary(
                        id=uid.decode("ascii"),
                        folder=folder,
                        subject=decode_header_text(message.get("Subject", "")),
                        sender=_first_address(message.get_all("From", [])),
                        recipients=_all_addresses(message.get_all("To", [])),
                        received_at=str(message.get("Date", "")),
                        is_read=b"\\Seen" in metadata_bytes,
                        has_attachments=b"ATTACHMENT" in metadata_bytes.upper(),
                        body_preview=preview,
                        id_mode="uid",
                    )
                )
            return items, offset + len(selected) < len(uids)
        finally:
            _logout(client)

    @classmethod
    def _raw_sync(
        cls,
        credentials: ImapCredentials,
        metadata: dict[str, Any],
        folder: str,
        message_id: str,
    ) -> bytes:
        return cls._raw_with_flags_sync(
            credentials,
            metadata,
            folder,
            message_id,
        )[0]

    @classmethod
    def _raw_with_flags_sync(
        cls,
        credentials: ImapCredentials,
        metadata: dict[str, Any],
        folder: str,
        message_id: str,
    ) -> tuple[bytes, bool]:
        _validate_uid(message_id)
        client = cls._connect_sync(credentials)
        try:
            _select_folder(client, metadata, folder, readonly=True)
            status, data = client.uid("fetch", message_id, "(RFC822 FLAGS)")
            if status != "OK" or not data:
                raise imaplib.IMAP4.error("UID fetch failed")
            payload, response_metadata = _fetch_payload(data)
            if not payload:
                raise imaplib.IMAP4.error("Message body is empty")
            return payload, b"\\Seen" in response_metadata
        finally:
            _logout(client)

    @classmethod
    def _store_sync(
        cls,
        credentials: ImapCredentials,
        metadata: dict[str, Any],
        folder: str,
        message_id: str,
        command: str,
        flags: str,
        expunge: bool,
    ) -> None:
        _validate_uid(message_id)
        client = cls._connect_sync(credentials)
        try:
            _select_folder(client, metadata, folder, readonly=False)
            status, _ = client.uid("store", message_id, command, flags)
            if status != "OK":
                raise imaplib.IMAP4.error("UID store failed")
            if expunge and client.expunge()[0] != "OK":
                raise imaplib.IMAP4.error("EXPUNGE failed")
        finally:
            _logout(client)


def _validate_uid(message_id: str) -> None:
    if not message_id.isdigit() or int(message_id) <= 0:
        raise ValueError("IMAP message id must be a positive UID")


def _select_folder(
    client: imaplib.IMAP4_SSL,
    metadata: dict[str, Any],
    folder: str,
    *,
    readonly: bool,
) -> str:
    folder_map = metadata.get("folder_map")
    configured = folder_map.get(folder) if isinstance(folder_map, dict) else None
    candidates = [str(configured)] if configured else FOLDER_CANDIDATES.get(folder, [])
    if not candidates:
        raise ValueError(f"Unsupported IMAP folder: {folder}")
    for candidate in candidates:
        status, _ = client.select(candidate, readonly=readonly)
        if status == "OK":
            return candidate
    raise imaplib.IMAP4.error(f"No selectable mailbox for {folder}")


def _fetch_payload(data: list[Any]) -> tuple[bytes, bytes]:
    payloads: list[bytes] = []
    metadata_parts: list[bytes] = []
    for part in data:
        if isinstance(part, tuple):
            if isinstance(part[0], bytes):
                metadata_parts.append(part[0])
            if isinstance(part[1], bytes):
                payloads.append(part[1])
        elif isinstance(part, bytes):
            metadata_parts.append(part)
    return b"\r\n".join(payloads), b" ".join(metadata_parts)


def decode_header_text(value: str) -> str:
    decoded: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(chunk))
    return "".join(decoded)


def _first_address(headers: list[str]) -> str:
    addresses = _all_addresses(headers)
    return addresses[0] if addresses else ""


def _all_addresses(headers: list[str]) -> list[str]:
    return [address for _name, address in getaddresses(headers) if address]


def _body_preview(payload: bytes) -> str:
    split = payload.split(b"\r\n\r\n", 1)
    body = split[1] if len(split) == 2 else b""
    text = body.decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", text).strip()[:500]


def attachment_parts(message: Message) -> list[Message]:
    return [
        part
        for part in message.walk()
        if part.get_filename() or part.get_content_disposition() == "attachment"
    ]


def decoded_payload(part: Message) -> bytes:
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else b""


def parse_message_detail(raw: bytes, *, message_id: str, folder: str) -> MailMessageDetail:
    message = email.message_from_bytes(raw, policy=default)
    message_attachments = attachment_parts(message)
    attachment_object_ids = {id(part) for part in message_attachments}
    text_body = ""
    html_body = ""
    for part in message.walk():
        if part.is_multipart() or id(part) in attachment_object_ids:
            continue
        content_type = part.get_content_type()
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError):
            content = decoded_payload(part).decode("utf-8", errors="replace")
        if content_type == "text/html" and not html_body:
            html_body = str(content)
        elif content_type == "text/plain" and not text_body:
            text_body = str(content)
    attachments = [
        MailAttachment(
            id=str(index),
            name=decode_header_text(part.get_filename() or "attachment"),
            content_type=part.get_content_type(),
            size=len(decoded_payload(part)),
            is_inline=part.get_content_disposition() == "inline",
        )
        for index, part in enumerate(message_attachments, 1)
    ]
    body = html_body or text_body
    return MailMessageDetail(
        id=message_id,
        folder=folder,
        subject=decode_header_text(message.get("Subject", "")),
        sender=_first_address(message.get_all("From", [])),
        recipients=_all_addresses(message.get_all("To", [])),
        cc=_all_addresses(message.get_all("Cc", [])),
        received_at=str(message.get("Date", "")),
        is_read=False,
        body=body,
        body_type="html" if html_body else "text",
        attachments=attachments,
        id_mode="uid",
    )


def _imap_failure(code: str, exc: Exception) -> ProviderOperationError:
    message = str(exc)[:300]
    normalized = message.lower()
    if "authenticated but not connected" in normalized:
        return ProviderOperationError(
            code="IMAP_SESSION_NOT_CONNECTED",
            message=message,
            status=503,
            retryable=True,
            details={"operation_code": code},
        )
    if any(marker in normalized for marker in ("temporarily unavailable", "try again later", "too many")):
        return ProviderOperationError(
            code="IMAP_TEMPORARILY_UNAVAILABLE",
            message=message,
            status=503,
            retryable=True,
            details={"operation_code": code},
        )
    return ProviderOperationError(
        code=code,
        message=message,
        status=502,
        retryable=isinstance(exc, (OSError, httpx.NetworkError, httpx.TimeoutException)),
    )


def _logout(client: imaplib.IMAP4_SSL) -> None:
    with suppress(Exception):
        client.logout()
