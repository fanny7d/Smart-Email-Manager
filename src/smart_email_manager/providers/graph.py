from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

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
from smart_email_manager.services.secrets import DecryptedAccountSecrets

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
GRAPH_ME_URL = f"{GRAPH_ROOT}/me"
GRAPH_FOLDERS = {
    "inbox": "inbox",
    "junkemail": "junkemail",
    "deleteditems": "deleteditems",
}


class GraphProvider:
    channel = "graph"

    def __init__(self, client_factory: Callable[[], httpx.AsyncClient] | None = None) -> None:
        self._client_factory = client_factory

    def _client(self, account: ProviderAccount) -> httpx.AsyncClient:
        if self._client_factory:
            return self._client_factory()
        configured = next((value for value in account.proxy_urls if value != "direct"), None)
        return httpx.AsyncClient(
            timeout=30,
            proxy=configured,
            trust_env=configured is None,
        )

    async def _access_token(
        self,
        client: httpx.AsyncClient,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> str:
        client_id = str(account.provider_metadata.get("client_id") or "").strip()
        if not client_id or not secrets.refresh_token:
            raise ProviderOperationError(
                code="GRAPH_CREDENTIALS_MISSING",
                message="client_id or refresh_token is missing",
                status=422,
            )
        payload = await self._token_payload(client, account, secrets)
        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise ProviderOperationError(
                code="GRAPH_TOKEN_MISSING",
                message="Microsoft token response did not include access_token",
            )
        return access_token

    async def _token_payload(
        self,
        client: httpx.AsyncClient,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> dict[str, Any]:
        client_id = str(account.provider_metadata.get("client_id") or "").strip()
        if not client_id or not secrets.refresh_token:
            raise ProviderOperationError(
                code="GRAPH_CREDENTIALS_MISSING",
                message="client_id or refresh_token is missing",
                status=422,
            )
        response = await client.post(
            GRAPH_TOKEN_URL,
            data={
                "client_id": client_id,
                "refresh_token": secrets.refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default offline_access",
            },
        )
        if response.status_code != 200:
            raise _operation_failure("GRAPH_TOKEN_REJECTED", response)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        try:
            async with self._client(account) as client:
                payload = await self._token_payload(client, account, secrets)
            if not payload.get("access_token"):
                return TokenRefreshResult(False, self.channel, "GRAPH_TOKEN_MISSING")
            return TokenRefreshResult(
                True,
                self.channel,
                "GRAPH_TOKEN_REFRESHED",
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
                details=exc.details,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return TokenRefreshResult(
                False,
                self.channel,
                "GRAPH_NETWORK_FAILED",
                message=str(exc)[:300],
                retryable=True,
            )

    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        try:
            async with self._client(account) as client:
                access_token = await self._access_token(client, account, secrets)
                response = await client.get(
                    GRAPH_ME_URL,
                    params={"$select": "id,mail,userPrincipalName"},
                    headers=_headers(access_token),
                )
                if response.status_code != 200:
                    raise _operation_failure("GRAPH_ACCESS_FAILED", response)
                profile = response.json()
                return ProviderHealthResult(
                    status="healthy",
                    channel=self.channel,
                    reason_code="GRAPH_OK",
                    details={
                        "mail": profile.get("mail") or profile.get("userPrincipalName") or "",
                    },
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
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return ProviderHealthResult(
                status="failed",
                channel=self.channel,
                reason_code="GRAPH_NETWORK_FAILED",
                message=str(exc)[:300],
                retryable=True,
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
        folder_name = _folder(folder)
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.get(
                f"{GRAPH_ROOT}/me/mailFolders/{folder_name}/messages",
                headers=_headers(token),
                params={
                    "$top": limit,
                    "$skip": offset,
                    "$select": (
                        "id,subject,from,toRecipients,receivedDateTime,isRead,hasAttachments,bodyPreview"
                    ),
                    "$orderby": "receivedDateTime desc",
                },
            )
            if response.status_code != 200:
                raise _operation_failure("GRAPH_MAIL_LIST_FAILED", response)
            items = [_summary(item, folder) for item in response.json().get("value", [])]
            return MailPage(items=items, has_more=len(items) >= limit, method=self.channel)

    async def get_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> MailMessageDetail:
        encoded_id = quote(message_id, safe="")
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.get(
                f"{GRAPH_ROOT}/me/messages/{encoded_id}",
                headers={**_headers(token), "Prefer": 'outlook.body-content-type="html"'},
                params={
                    "$select": (
                        "id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
                        "isRead,body,hasAttachments"
                    )
                },
            )
            if response.status_code != 200:
                raise _operation_failure("GRAPH_MAIL_DETAIL_FAILED", response)
            item = response.json()
            attachments = await self._list_attachments(client, token, encoded_id)
            body = item.get("body") or {}
            return MailMessageDetail(
                id=str(item.get("id") or message_id),
                folder=folder,
                subject=str(item.get("subject") or ""),
                sender=_address(item.get("from")),
                recipients=_addresses(item.get("toRecipients")),
                cc=_addresses(item.get("ccRecipients")),
                received_at=str(item.get("receivedDateTime") or ""),
                is_read=bool(item.get("isRead")),
                body=str(body.get("content") or ""),
                body_type="html" if str(body.get("contentType") or "").lower() == "html" else "text",
                attachments=attachments,
                id_mode="graph",
            )

    async def _list_attachments(
        self,
        client: httpx.AsyncClient,
        token: str,
        encoded_message_id: str,
    ) -> list[MailAttachment]:
        response = await client.get(
            f"{GRAPH_ROOT}/me/messages/{encoded_message_id}/attachments",
            headers=_headers(token),
            params={"$select": "id,name,contentType,size,isInline"},
        )
        if response.status_code != 200:
            raise _operation_failure("GRAPH_ATTACHMENT_LIST_FAILED", response)
        return [
            MailAttachment(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or "attachment"),
                content_type=str(item.get("contentType") or "application/octet-stream"),
                size=int(item.get("size") or 0),
                is_inline=bool(item.get("isInline")),
            )
            for item in response.json().get("value", [])
        ]

    async def get_raw_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> bytes:
        del folder
        encoded_id = quote(message_id, safe="")
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.get(
                f"{GRAPH_ROOT}/me/messages/{encoded_id}/$value",
                headers=_headers(token),
            )
            if response.status_code != 200:
                raise _operation_failure("GRAPH_RAW_MAIL_FAILED", response)
            return response.content

    async def download_attachment(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
        attachment_id: str,
    ) -> DownloadedAttachment:
        del folder
        encoded_message_id = quote(message_id, safe="")
        encoded_attachment_id = quote(attachment_id, safe="")
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.get(
                f"{GRAPH_ROOT}/me/messages/{encoded_message_id}/attachments/{encoded_attachment_id}",
                headers=_headers(token),
            )
            if response.status_code != 200:
                raise _operation_failure("GRAPH_ATTACHMENT_DOWNLOAD_FAILED", response)
            item = response.json()
            content = str(item.get("contentBytes") or "")
            if not content:
                raise ProviderOperationError(
                    code="GRAPH_ATTACHMENT_CONTENT_MISSING",
                    message="Attachment is not a downloadable file attachment.",
                    status=422,
                )
            try:
                decoded = base64.b64decode(content, validate=True)
            except ValueError as exc:
                raise ProviderOperationError(
                    code="GRAPH_ATTACHMENT_CONTENT_INVALID",
                    message="Attachment content is not valid base64.",
                ) from exc
            return DownloadedAttachment(
                name=str(item.get("name") or "attachment"),
                content_type=str(item.get("contentType") or "application/octet-stream"),
                content=decoded,
            )

    async def mark_read(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None:
        del folder
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.patch(
                f"{GRAPH_ROOT}/me/messages/{quote(message_id, safe='')}",
                headers=_headers(token),
                json={"isRead": True},
            )
            if response.status_code not in {200, 204}:
                raise _operation_failure("GRAPH_MARK_READ_FAILED", response)

    async def delete_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None:
        del folder
        async with self._client(account) as client:
            token = await self._access_token(client, account, secrets)
            response = await client.delete(
                f"{GRAPH_ROOT}/me/messages/{quote(message_id, safe='')}",
                headers=_headers(token),
            )
            if response.status_code != 204:
                raise _operation_failure("GRAPH_DELETE_FAILED", response)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _folder(folder: str) -> str:
    try:
        return GRAPH_FOLDERS[folder]
    except KeyError as exc:
        raise ProviderOperationError(
            code="MAIL_FOLDER_INVALID",
            message=f"Unsupported Graph folder: {folder}",
            status=400,
        ) from exc


def _address(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    address = value.get("emailAddress")
    if not isinstance(address, dict):
        return ""
    return str(address.get("address") or address.get("name") or "")


def _addresses(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [address for item in value if (address := _address(item))]


def _summary(item: dict[str, Any], folder: str) -> MailMessageSummary:
    return MailMessageSummary(
        id=str(item.get("id") or ""),
        folder=folder,
        subject=str(item.get("subject") or ""),
        sender=_address(item.get("from")),
        recipients=_addresses(item.get("toRecipients")),
        received_at=str(item.get("receivedDateTime") or ""),
        is_read=bool(item.get("isRead")),
        has_attachments=bool(item.get("hasAttachments")),
        body_preview=str(item.get("bodyPreview") or ""),
        id_mode="graph",
    )


def _operation_failure(code: str, response: httpx.Response) -> ProviderOperationError:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or "")
        else:
            message = str(payload)[:300]
    except ValueError:
        message = response.text[:300]
    return ProviderOperationError(
        code=code,
        message=message or f"HTTP {response.status_code}",
        status=response.status_code if 400 <= response.status_code < 500 else 502,
        retryable=response.status_code >= 500 or response.status_code == 429,
        details={"http_status": response.status_code},
    )
