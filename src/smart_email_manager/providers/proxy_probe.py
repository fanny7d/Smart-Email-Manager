from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

PROBE_URL = "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"


@dataclass(frozen=True)
class ProxyProbeResult:
    success: bool
    reason_code: str
    latency_ms: int
    message: str = ""


class ProxyProber:
    def __init__(
        self,
        client_factory: Callable[[str], httpx.AsyncClient] | None = None,
    ) -> None:
        self._client_factory = client_factory

    def _client(self, proxy_url: str) -> httpx.AsyncClient:
        if self._client_factory:
            return self._client_factory(proxy_url)
        return httpx.AsyncClient(
            proxy=proxy_url,
            timeout=15,
            trust_env=False,
            follow_redirects=True,
        )

    async def probe(self, proxy_url: str) -> ProxyProbeResult:
        started = time.monotonic()
        try:
            async with self._client(proxy_url) as client:
                response = await client.get(PROBE_URL)
            latency = round((time.monotonic() - started) * 1000)
            if response.status_code == 200:
                return ProxyProbeResult(True, "PROXY_OK", latency)
            return ProxyProbeResult(
                False,
                "PROXY_HTTP_FAILED",
                latency,
                f"Probe endpoint returned HTTP {response.status_code}",
            )
        except (httpx.HTTPError, ValueError) as exc:
            latency = round((time.monotonic() - started) * 1000)
            return ProxyProbeResult(False, "PROXY_CONNECT_FAILED", latency, str(exc)[:300])
