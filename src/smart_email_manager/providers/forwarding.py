from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any


@dataclass(frozen=True)
class ForwardPayload:
    subject: str
    text: str
    html: str = ""


@dataclass(frozen=True)
class ForwardResult:
    success: bool
    channel: str
    reason_code: str
    message: str = ""
    retryable: bool = False


class ForwardingSender:
    async def send(
        self,
        *,
        channel: str,
        config: dict[str, Any],
        secret: str,
        payload: ForwardPayload,
    ) -> ForwardResult:
        if channel == "smtp":
            return await asyncio.to_thread(self._send_smtp, config, secret, payload)
        return ForwardResult(False, channel, "FORWARD_CHANNEL_UNSUPPORTED")

    @staticmethod
    def _send_smtp(
        config: dict[str, Any],
        password: str,
        payload: ForwardPayload,
    ) -> ForwardResult:
        host = str(config.get("host") or "")
        port = int(config.get("port") or (465 if config.get("use_ssl", True) else 587))
        username = str(config.get("username") or "")
        recipient = str(config.get("recipient") or "")
        from_email = str(config.get("from_email") or username)
        message = EmailMessage()
        message["From"] = from_email
        message["To"] = recipient
        message["Subject"] = payload.subject
        message.set_content(payload.text)
        if payload.html:
            message.add_alternative(payload.html, subtype="html")
        try:
            smtp_type = smtplib.SMTP_SSL if bool(config.get("use_ssl", True)) else smtplib.SMTP
            with smtp_type(host, port, timeout=20) as client:
                if not bool(config.get("use_ssl", True)):
                    client.ehlo()
                    if bool(config.get("use_tls", False)):
                        client.starttls()
                        client.ehlo()
                if username:
                    client.login(username, password)
                client.send_message(message)
            return ForwardResult(True, "smtp", "SMTP_SENT")
        except (OSError, smtplib.SMTPException) as exc:
            retryable = isinstance(
                exc,
                (OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected),
            )
            return ForwardResult(
                False,
                "smtp",
                "SMTP_SEND_FAILED",
                str(exc)[:300],
                retryable=retryable,
            )
