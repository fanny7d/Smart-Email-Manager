from __future__ import annotations

import ssl
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx

from smart_email_manager.cli.config import load_cli_config


def _segment(value: str) -> str:
    return quote(value, safe="")


class SmartEmailManagerClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        config_path: Path | None = None,
        token_file: Path | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        config = load_cli_config(
            config_path,
            api_url=base_url,
            token_file=token_file,
            timeout_seconds=timeout_seconds,
            load_token=token is None,
        )
        self.base_url = config.api_url
        self.token = token if token is not None else config.token
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        verify: bool | ssl.SSLContext = True
        if config.ca_bundle:
            verify = ssl.create_default_context(cafile=config.ca_bundle)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=config.timeout_seconds,
            verify=verify,
        )

    def __enter__(self) -> SmartEmailManagerClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = {"detail": response.text}
            raise httpx.HTTPStatusError(
                f"{response.status_code}: {detail.get('detail') or detail}",
                request=response.request,
                response=response,
            )
        return cast(dict[str, Any], response.json())

    def _request_list(self, method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        response = self._client.request(method, path, **kwargs)
        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = {"detail": response.text}
            raise httpx.HTTPStatusError(
                f"{response.status_code}: {detail.get('detail') or detail}",
                request=response.request,
                response=response,
            )
        return cast(list[dict[str, Any]], response.json())

    def system_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/system/health")

    def create_api_token(
        self,
        *,
        name: str,
        scopes: list[str],
        expires_in_days: int | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/auth/tokens",
            json={"name": name, "scopes": scopes, "expires_in_days": expires_in_days},
        )

    def list_api_tokens(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/auth/tokens")}

    def revoke_api_token(self, token_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/auth/tokens/{token_id}/revoke")

    def fleet_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/fleet/summary")

    def list_account_views(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/fleet/views")

    def create_saved_account_view(
        self,
        *,
        name: str,
        filters: dict[str, Any],
        sort_order: int,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/fleet/views",
            json={"name": name, "filters": filters, "sort_order": sort_order},
        )

    def update_saved_account_view(
        self,
        view_id: uuid.UUID,
        *,
        name: str | None,
        filters: dict[str, Any] | None,
        sort_order: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            key: value
            for key, value in {
                "name": name,
                "filters": filters,
                "sort_order": sort_order,
            }.items()
            if value is not None
        }
        return self._request("PUT", f"/api/v1/fleet/views/{view_id}", json=payload)

    def delete_saved_account_view(self, view_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/fleet/views/{view_id}")
        response.raise_for_status()

    def list_groups(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/groups")}

    def create_group(
        self,
        *,
        name: str,
        parent_id: uuid.UUID | None,
        description: str,
        color: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/groups",
            json={
                "name": name,
                "parent_id": str(parent_id) if parent_id else None,
                "description": description,
                "color": color,
            },
        )

    def update_group(
        self,
        group_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
        color: str | None,
        parent_id: uuid.UUID | None,
        move_parent: bool,
        sort_order: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            key: value
            for key, value in {
                "name": name,
                "description": description,
                "color": color,
                "sort_order": sort_order,
            }.items()
            if value is not None
        }
        if move_parent:
            payload["parent_id"] = str(parent_id) if parent_id else None
        return self._request("PUT", f"/api/v1/groups/{group_id}", json=payload)

    def delete_group(self, group_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/groups/{group_id}")
        response.raise_for_status()

    def list_tags(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/tags")}

    def create_tag(self, *, name: str, color: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/tags", json={"name": name, "color": color})

    def delete_tag(self, tag_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/tags/{tag_id}")
        response.raise_for_status()

    def list_aliases(self, account_id: uuid.UUID) -> dict[str, Any]:
        return {"items": self._request_list("GET", f"/api/v1/accounts/{account_id}/aliases")}

    def replace_aliases(self, account_id: uuid.UUID, aliases: list[str]) -> dict[str, Any]:
        return {
            "items": self._request_list(
                "PUT",
                f"/api/v1/accounts/{account_id}/aliases",
                json={"aliases": aliases},
            )
        }

    def list_account_tags(self, account_id: uuid.UUID) -> dict[str, Any]:
        return {"items": self._request_list("GET", f"/api/v1/accounts/{account_id}/tags")}

    def mutate_account_tags(
        self,
        account_id: uuid.UUID,
        *,
        action: str,
        tag_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        return {
            "items": self._request_list(
                "PUT",
                f"/api/v1/accounts/{account_id}/tags",
                json={"action": action, "tag_ids": [str(item) for item in tag_ids]},
            )
        }

    def list_proxy_profiles(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/proxies")}

    def create_proxy_profile(
        self,
        *,
        name: str,
        primary_url: str,
        fallback_url_1: str | None,
        fallback_url_2: str | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/proxies",
            json={
                "name": name,
                "primary_url": primary_url,
                "fallback_url_1": fallback_url_1,
                "fallback_url_2": fallback_url_2,
                "enabled": True,
            },
        )

    def update_proxy_profile(
        self,
        profile_id: uuid.UUID,
        *,
        name: str,
        primary_url: str,
        fallback_url_1: str | None,
        fallback_url_2: str | None,
        enabled: bool,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/proxies/{profile_id}",
            json={
                "name": name,
                "primary_url": primary_url,
                "fallback_url_1": fallback_url_1,
                "fallback_url_2": fallback_url_2,
                "enabled": enabled,
            },
        )

    def delete_proxy_profile(self, profile_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/proxies/{profile_id}")
        response.raise_for_status()

    def assign_proxy(self, resource: str, resource_id: uuid.UUID, profile_id: uuid.UUID | None) -> None:
        response = self._client.put(
            f"/api/v1/proxies/{resource}/{resource_id}",
            json={"proxy_profile_id": str(profile_id) if profile_id else None},
        )
        response.raise_for_status()

    def resolve_proxy(self, account_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/proxies/accounts/{account_id}/resolved")

    def probe_proxy(self, profile_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/proxies/{profile_id}/probe")

    def list_accounts(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        lifecycle_status: str | None = None,
        token_status: str | None = None,
        mail_health_status: str | None = None,
        query: str | None = None,
        view: str | None = None,
        saved_view_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        params = {
            key: value
            for key, value in {
                "limit": limit,
                "cursor": cursor,
                "lifecycle_status": lifecycle_status,
                "token_status": token_status,
                "mail_health_status": mail_health_status,
                "query": query,
                "view": view,
                "saved_view_id": str(saved_view_id) if saved_view_id else None,
            }.items()
            if value is not None
        }
        return self._request("GET", "/api/v1/accounts", params=params)

    def create_account(
        self,
        *,
        email: str,
        account_type: str,
        provider: str,
        remark: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/accounts",
            json={
                "email": email,
                "account_type": account_type,
                "provider": provider,
                "remark": remark,
            },
        )

    def get_account(self, account_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/accounts/{account_id}")

    def get_account_secrets_status(self, account_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/accounts/{account_id}/secrets/status")

    def write_account_secrets(
        self,
        account_id: uuid.UUID,
        *,
        password: str | None,
        refresh_token: str | None,
    ) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in {"password": password, "refresh_token": refresh_token}.items()
            if value is not None
        }
        return self._request("PUT", f"/api/v1/accounts/{account_id}/secrets", json=payload)

    def update_account(
        self,
        account_id: uuid.UUID,
        *,
        row_version: int,
        lifecycle_status: str | None,
        group_id: uuid.UUID | None,
        move_group: bool,
        remark: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"row_version": row_version}
        if lifecycle_status is not None:
            payload["lifecycle_status"] = lifecycle_status
        if move_group:
            payload["group_id"] = str(group_id) if group_id else None
        if remark is not None:
            payload["remark"] = remark
        return self._request("PATCH", f"/api/v1/accounts/{account_id}", json=payload)

    def bulk_mutate_accounts(
        self,
        account_ids: list[uuid.UUID],
        *,
        lifecycle_status: str | None,
        group_id: uuid.UUID | None,
        move_group: bool,
        add_tag_ids: list[uuid.UUID],
        remove_tag_ids: list[uuid.UUID],
        forwarding_enabled: bool | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/accounts/bulk/mutations",
            json={
                "account_ids": [str(item) for item in account_ids],
                "lifecycle_status": lifecycle_status,
                "move_group": move_group,
                "group_id": str(group_id) if group_id else None,
                "add_tag_ids": [str(item) for item in add_tag_ids],
                "remove_tag_ids": [str(item) for item in remove_tag_ids],
                "forwarding_enabled": forwarding_enabled,
            },
        )

    def preview_bulk_accounts(
        self,
        *,
        selection: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/accounts/bulk/previews",
            json={"selection": selection, "changes": changes},
        )

    def execute_bulk_preview(self, preview_token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/accounts/bulk/executions",
            json={"preview_token": preview_token},
        )

    def archive_account(self, account_id: uuid.UUID, row_version: int) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/accounts/{account_id}/archive",
            json={"row_version": row_version},
        )

    def purge_account(self, account_id: uuid.UUID, confirm_email: str) -> None:
        response = self._client.delete(
            f"/api/v1/accounts/{account_id}",
            params={"confirm_email": confirm_email},
        )
        response.raise_for_status()

    def create_health_check(
        self,
        account_ids: list[uuid.UUID],
        *,
        limit: int,
        mode: str = "metadata",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request(
            "POST",
            "/api/v1/health-check-jobs",
            json={"account_ids": [str(item) for item in account_ids], "limit": limit, "mode": mode},
            headers=headers,
        )

    def create_token_refresh(
        self,
        account_ids: list[uuid.UUID],
        *,
        failed_only: bool,
        limit: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request(
            "POST",
            "/api/v1/token-refresh-jobs",
            json={
                "account_ids": [str(item) for item in account_ids],
                "failed_only": failed_only,
                "limit": limit,
            },
            headers=headers,
        )

    def write_retention_policy(
        self,
        account_id: uuid.UUID,
        *,
        enabled: bool,
        retain_bodies: bool,
        folders: list[str],
        max_messages: int,
        max_age_days: int,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/retention/accounts/{account_id}/policy",
            json={
                "enabled": enabled,
                "retain_bodies": retain_bodies,
                "folders": folders,
                "max_messages": max_messages,
                "max_age_days": max_age_days,
            },
        )

    def list_retention_policies(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/retention/policies")}

    def get_retention_policy(self, account_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/retention/accounts/{account_id}/policy")

    def list_retained_mail(
        self,
        account_id: uuid.UUID,
        *,
        folder: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/retention/accounts/{account_id}/mail",
            params={"folder": folder, "offset": offset, "limit": limit},
        )

    def get_retained_mail(
        self,
        account_id: uuid.UUID,
        message_id: str,
        *,
        folder: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/retention/accounts/{account_id}/mail/{_segment(message_id)}",
            params={"folder": folder},
        )

    def clear_retained_mail(self, account_id: uuid.UUID | None) -> None:
        params = {"account_id": str(account_id)} if account_id else None
        response = self._client.delete("/api/v1/retention/cache", params=params)
        response.raise_for_status()

    def retention_stats(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/retention/stats")

    def create_retention_sync(
        self,
        account_ids: list[uuid.UUID],
        *,
        limit: int,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request(
            "POST",
            "/api/v1/retention/sync-jobs",
            json={"account_ids": [str(item) for item in account_ids], "limit": limit},
            headers=headers,
        )

    def create_email_share(
        self,
        account_id: uuid.UUID,
        *,
        duration_minutes: int,
        never_expires: bool,
        allowed_folders: list[str],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/email-shares",
            json={
                "account_id": str(account_id),
                "duration_minutes": duration_minutes,
                "never_expires": never_expires,
                "allowed_folders": allowed_folders,
            },
        )

    def get_public_share_status(self, token: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/public/email-shares/{_segment(token)}/status")

    def list_public_share_mail(
        self,
        token: str,
        *,
        folder: str,
        source: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/public/email-shares/{_segment(token)}/mail",
            params={"folder": folder, "source": source, "offset": offset, "limit": limit},
        )

    def get_public_share_mail(
        self,
        token: str,
        message_id: str,
        *,
        folder: str,
        source: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/public/email-shares/{_segment(token)}/mail/{_segment(message_id)}",
            params={"folder": folder, "source": source},
        )

    def list_forwarding_destinations(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/forwarding/destinations")}

    def create_forwarding_destination(
        self,
        *,
        name: str,
        channel: str,
        config: dict[str, str | int | bool],
        secret: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/forwarding/destinations",
            json={
                "name": name,
                "channel": channel,
                "config": config,
                "secret": secret,
            },
        )

    def update_forwarding_destination(
        self,
        destination_id: uuid.UUID,
        *,
        name: str,
        config: dict[str, str | int | bool],
        secret: str | None,
        enabled: bool,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/forwarding/destinations/{destination_id}",
            json={
                "name": name,
                "channel": "smtp",
                "enabled": enabled,
                "config": config,
                "secret": secret,
            },
        )

    def test_forwarding_destination(self, destination_id: uuid.UUID) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/v1/forwarding/destinations/{destination_id}/test"
        )

    def delete_forwarding_destination(self, destination_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/forwarding/destinations/{destination_id}")
        response.raise_for_status()

    def get_account_forwarding(self, account_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/forwarding/accounts/{account_id}")

    def write_account_forwarding(
        self,
        account_id: uuid.UUID,
        *,
        enabled: bool,
        include_junk: bool,
        window_minutes: int,
        destination_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/forwarding/accounts/{account_id}",
            json={
                "enabled": enabled,
                "include_junk": include_junk,
                "window_minutes": window_minutes,
                "destination_ids": [str(item) for item in destination_ids],
            },
        )

    def reset_forwarding_cursor(
        self,
        account_id: uuid.UUID,
        cursor_at: str | None,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/forwarding/accounts/{account_id}/cursor",
            json={"cursor_at": cursor_at},
        )

    def create_forwarding_job(
        self,
        account_ids: list[uuid.UUID],
        *,
        limit: int,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request(
            "POST",
            "/api/v1/forwarding/jobs",
            json={"account_ids": [str(item) for item in account_ids], "limit": limit},
            headers=headers,
        )

    def list_forwarding_deliveries(
        self,
        *,
        account_id: uuid.UUID | None,
        limit: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"limit": limit}
        if account_id:
            params["account_id"] = str(account_id)
        return {"items": self._request_list("GET", "/api/v1/forwarding/deliveries", params=params)}

    def list_email_shares(self, account_id: uuid.UUID | None) -> dict[str, Any]:
        params = {"account_id": str(account_id)} if account_id else None
        return {"items": self._request_list("GET", "/api/v1/email-shares", params=params)}

    def revoke_email_share(self, share_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/email-shares/{share_id}/revoke")

    def delete_email_share(self, share_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/email-shares/{share_id}")
        response.raise_for_status()

    def list_token_refresh_logs(
        self,
        *,
        account_id: uuid.UUID | None,
        limit: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"limit": limit}
        if account_id:
            params["account_id"] = str(account_id)
        return {"items": self._request_list("GET", "/api/v1/token-refresh-logs", params=params)}

    def token_refresh_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/token-refresh-summary")

    def list_schedules(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/schedules")}

    def write_schedule(
        self,
        *,
        name: str,
        cron_expression: str,
        timezone: str,
        task_type: str,
        enabled: bool,
        failed_only: bool,
        limit: int,
        account_ids: list[uuid.UUID],
        schedule_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        method = "PUT" if schedule_id else "POST"
        path = f"/api/v1/schedules/{schedule_id}" if schedule_id else "/api/v1/schedules"
        payload: dict[str, Any]
        if task_type == "token_refresh":
            payload = {
                "account_ids": [str(item) for item in account_ids],
                "failed_only": failed_only,
                "limit": limit,
            }
        else:
            payload = {
                "account_ids": [str(item) for item in account_ids],
                "limit": limit,
            }
        return self._request(
            method,
            path,
            json={
                "name": name,
                "task_type": task_type,
                "cron_expression": cron_expression,
                "timezone": timezone,
                "enabled": enabled,
                "payload": payload,
            },
        )

    def delete_schedule(self, schedule_id: uuid.UUID) -> None:
        response = self._client.delete(f"/api/v1/schedules/{schedule_id}")
        response.raise_for_status()

    def create_import_batch(
        self,
        *,
        content: str,
        account_type: str,
        provider: str,
        group_id: uuid.UUID | None,
        remark: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request(
            "POST",
            "/api/v1/import-batches",
            headers=headers,
            json={
                "content": content,
                "account_type": account_type,
                "provider": provider,
                "group_id": str(group_id) if group_id else None,
                "remark": remark,
            },
        )

    def list_import_batches(self, limit: int = 50) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/import-batches", params={"limit": limit})}

    def get_import_batch(self, batch_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/import-batches/{batch_id}")

    def commit_import_batch(self, batch_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/import-batches/{batch_id}/commit")

    def rollback_import_batch(self, batch_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/import-batches/{batch_id}/rollback")

    def list_mail(
        self,
        account_id: uuid.UUID,
        *,
        folder: str,
        method: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/accounts/{account_id}/mail",
            params={"folder": folder, "method": method, "offset": offset, "limit": limit},
        )

    def list_verification_codes(
        self,
        account_id: uuid.UUID,
        *,
        recent_minutes: int,
        messages_per_account: int,
        include_junk: bool,
        method: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/accounts/{account_id}/verification-codes",
            params={
                "recent_minutes": recent_minutes,
                "messages_per_account": messages_per_account,
                "include_junk": include_junk,
                "method": method,
            },
        )

    def query_verification_codes(
        self,
        *,
        account_ids: list[uuid.UUID],
        recent_minutes: int,
        messages_per_account: int,
        account_limit: int,
        include_junk: bool,
        method: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/verification-codes/query",
            json={
                "account_ids": [str(item) for item in account_ids],
                "recent_minutes": recent_minutes,
                "messages_per_account": messages_per_account,
                "account_limit": account_limit,
                "include_junk": include_junk,
                "method": method,
            },
        )

    def get_mail(
        self,
        account_id: uuid.UUID,
        message_id: str,
        *,
        folder: str,
        method: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/accounts/{account_id}/mail/messages/{_segment(message_id)}",
            params={"folder": folder, "method": method},
        )

    def download_mail_resource(
        self,
        account_id: uuid.UUID,
        message_id: str,
        *,
        folder: str,
        method: str,
        attachment_id: str | None = None,
    ) -> bytes:
        suffix = f"/attachments/{_segment(attachment_id)}" if attachment_id else "/raw"
        response = self._client.get(
            f"/api/v1/accounts/{account_id}/mail/messages/{_segment(message_id)}{suffix}",
            params={"folder": folder, "method": method},
        )
        response.raise_for_status()
        return response.content

    def mark_mail_read(
        self,
        account_id: uuid.UUID,
        message_id: str,
        *,
        folder: str,
        method: str,
    ) -> None:
        response = self._client.post(
            f"/api/v1/accounts/{account_id}/mail/messages/{_segment(message_id)}/read",
            params={"folder": folder, "method": method},
        )
        response.raise_for_status()

    def delete_mail(
        self,
        account_id: uuid.UUID,
        message_id: str,
        *,
        folder: str,
        method: str,
    ) -> None:
        response = self._client.delete(
            f"/api/v1/accounts/{account_id}/mail/messages/{_segment(message_id)}",
            params={"folder": folder, "method": method},
        )
        response.raise_for_status()

    def rotate_master_key(
        self,
        *,
        old_master_key: str,
        old_key_version: int,
        commit: bool,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/security/master-key-rotations",
            json={
                "old_master_key": old_master_key,
                "old_key_version": old_key_version,
                "commit": commit,
            },
        )

    def list_projects(self) -> dict[str, Any]:
        return {"items": self._request_list("GET", "/api/v1/projects")}

    def list_project_accounts(self, project_id: uuid.UUID) -> dict[str, Any]:
        return {
            "items": self._request_list(
                "GET",
                f"/api/v1/projects/{project_id}/accounts",
                params={"limit": 5000},
            )
        }

    def add_project_accounts(
        self,
        project_id: uuid.UUID,
        account_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/projects/{project_id}/accounts",
            json={"account_ids": [str(item) for item in account_ids]},
        )

    def set_project_status(self, project_id: uuid.UUID, status: str) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/v1/projects/{project_id}/status",
            json={"status": status},
        )

    def list_project_events(
        self,
        project_id: uuid.UUID,
        *,
        after: int,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "items": self._request_list(
                "GET",
                f"/api/v1/projects/{project_id}/events",
                params={"after": after, "limit": limit},
            )
        }

    def mutate_project_accounts(
        self,
        project_id: uuid.UUID,
        *,
        action: str,
        project_account_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/projects/{project_id}/account-actions",
            json={
                "action": action,
                "project_account_ids": [str(item) for item in project_account_ids],
            },
        )

    def create_project(
        self,
        *,
        name: str,
        description: str,
        lease_seconds: int,
        account_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/projects",
            json={
                "name": name,
                "description": description,
                "default_lease_seconds": lease_seconds,
                "account_ids": [str(item) for item in account_ids],
            },
        )

    def claim_project(
        self,
        project_id: uuid.UUID,
        *,
        owner: str,
        lease_seconds: int | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/projects/{project_id}/claims",
            json={"owner": owner, "lease_seconds": lease_seconds},
        )

    def project_lease_action(
        self,
        project_account_id: uuid.UUID,
        *,
        action: str,
        claim_token: str,
        result: dict[str, object] | None = None,
        error_summary: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/projects/leases/{project_account_id}/{action}",
            json={
                "claim_token": claim_token,
                "result": result or {},
                "error_summary": error_summary,
            },
        )

    def heartbeat_project_lease(
        self,
        project_account_id: uuid.UUID,
        *,
        claim_token: str,
        lease_seconds: int | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/projects/leases/{project_account_id}/heartbeat",
            json={"claim_token": claim_token, "lease_seconds": lease_seconds},
        )

    def get_job(self, job_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def pause_job(self, job_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/jobs/{job_id}/pause")

    def resume_job(self, job_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/jobs/{job_id}/resume")

    def cancel_job(self, job_id: uuid.UUID) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/jobs/{job_id}/cancel")

    def list_audit_logs(
        self,
        *,
        resource_type: str | None,
        resource_id: str | None,
        limit: int,
    ) -> dict[str, Any]:
        params = {
            key: value
            for key, value in {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "limit": limit,
            }.items()
            if value is not None
        }
        return {"items": self._request_list("GET", "/api/v1/audit-logs", params=params)}

    def list_jobs(self, limit: int = 50, status: str | None = None) -> dict[str, Any]:
        params: dict[str, str | int] = {"limit": limit}
        if status:
            params["status"] = status
        return {"items": self._request_list("GET", "/api/v1/jobs", params=params)}

    def get_job_events(self, job_id: uuid.UUID, after_sequence: int = 0) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/jobs/{job_id}/events",
            params={"after_sequence": after_sequence},
        )

    def watch_job(self, job_id: uuid.UUID) -> Iterator[dict[str, Any]]:
        terminal = {"completed", "partial", "failed", "cancelled"}
        sequence = 0
        while True:
            events = self.get_job_events(job_id, sequence)
            for event in events.get("items", []):
                sequence = max(sequence, int(event["sequence"]))
                yield event
            if self.get_job(job_id)["status"] in terminal:
                return
            import time

            time.sleep(1)
