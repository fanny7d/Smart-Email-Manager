from __future__ import annotations

from dataclasses import replace

from smart_email_manager.providers.base import (
    MailProvider,
    ProviderAccount,
    ProviderHealthResult,
    TokenRefreshResult,
)
from smart_email_manager.providers.graph import GraphProvider
from smart_email_manager.providers.imap import ImapProvider
from smart_email_manager.services.secrets import DecryptedAccountSecrets


class ProviderRegistry:
    def __init__(
        self,
        *,
        graph: GraphProvider | None = None,
        oauth_imap: ImapProvider | None = None,
    ) -> None:
        self.graph = graph or GraphProvider()
        self.oauth_imap = oauth_imap or ImapProvider()

    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        providers = (
            (self.oauth_imap, self.graph)
            if account.authorization_type == "imap"
            else (self.graph, self.oauth_imap)
        )
        failures: list[ProviderHealthResult] = []
        for provider in providers:
            for account_attempt in proxy_variants(account):
                result = await provider.check_health(account_attempt, secrets)
                if result.success:
                    return result
                failures.append(result)
        return ProviderHealthResult(
            status="failed",
            channel="all",
            reason_code="ALL_PROVIDER_CHANNELS_FAILED",
            message="All Outlook provider channels failed.",
            retryable=any(item.retryable for item in failures),
            details={
                "attempts": [
                    {
                        "channel": item.channel,
                        "reason_code": item.reason_code,
                        "message": item.message,
                    }
                    for item in failures
                ]
            },
        )

    def ordered_providers(
        self,
        account: ProviderAccount,
        requested_method: str | None = None,
    ) -> list[MailProvider]:
        if requested_method == "graph":
            return [self.graph]
        if requested_method == "imap":
            return [self.oauth_imap]
        return (
            [self.oauth_imap, self.graph]
            if account.authorization_type == "imap"
            else [self.graph, self.oauth_imap]
        )

    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        attempts: list[TokenRefreshResult] = []
        for provider in self.ordered_providers(account, None):
            for account_attempt in proxy_variants(account):
                result = await provider.refresh_authorization(account_attempt, secrets)
                if result.success:
                    return result
                attempts.append(result)
        return TokenRefreshResult(
            False,
            "all",
            "ALL_TOKEN_REFRESH_CHANNELS_FAILED",
            message="All token refresh channels failed.",
            retryable=any(item.retryable for item in attempts),
            details={
                "attempts": [
                    {
                        "channel": item.channel,
                        "reason_code": item.reason_code,
                        "message": item.message,
                    }
                    for item in attempts
                ]
            },
        )


def proxy_variants(account: ProviderAccount) -> list[ProviderAccount]:
    if not account.proxy_urls:
        return [account]
    return [
        replace(account, proxy_urls=() if value == "direct" else (value,)) for value in account.proxy_urls
    ]
