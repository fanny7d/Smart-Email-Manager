from __future__ import annotations

import base64
import binascii
import hashlib
import os
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.config import Settings

NONCE_SIZE = 12


@dataclass(frozen=True)
class EncryptedValue:
    ciphertext: bytes
    key_version: int


class AccountSecretCipher:
    def __init__(self, key: bytes, key_version: int) -> None:
        if len(key) != 32:
            raise ValueError("account master key must decode to exactly 32 bytes")
        self._cipher = AESGCM(key)
        self.key_version = key_version

    @classmethod
    def from_settings(cls, settings: Settings) -> AccountSecretCipher:
        if not settings.master_key:
            if settings.environment == "development":
                development_key = hashlib.sha256(b"smart-email-manager-local-development-key-v1").digest()
                return cls(development_key, settings.master_key_version)
            raise ApiProblem(
                status=503,
                code="MASTER_KEY_NOT_CONFIGURED",
                title="Account encryption is not configured",
                detail="Configure SEM_MASTER_KEY before writing account secrets.",
            )
        encoded = settings.master_key.get_secret_value().encode("ascii")
        try:
            key = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise ApiProblem(
                status=503,
                code="MASTER_KEY_INVALID",
                title="Account encryption key is invalid",
                detail="SEM_MASTER_KEY must be URL-safe base64 for exactly 32 bytes.",
            ) from exc
        if len(key) != 32:
            raise ApiProblem(
                status=503,
                code="MASTER_KEY_INVALID",
                title="Account encryption key is invalid",
                detail="SEM_MASTER_KEY must decode to exactly 32 bytes.",
            )
        return cls(key, settings.master_key_version)

    @staticmethod
    def _aad(account_id: uuid.UUID, field_name: str, key_version: int) -> bytes:
        return f"smart-email-manager:account:{account_id}:{field_name}:v{key_version}".encode()

    @staticmethod
    def _context_aad(context: str, field_name: str, key_version: int) -> bytes:
        return f"smart-email-manager:{context}:{field_name}:v{key_version}".encode()

    def encrypt_context(self, context: str, field_name: str, value: str) -> EncryptedValue:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._cipher.encrypt(
            nonce,
            value.encode("utf-8"),
            self._context_aad(context, field_name, self.key_version),
        )
        return EncryptedValue(nonce + ciphertext, self.key_version)

    def decrypt_context(
        self,
        context: str,
        field_name: str,
        ciphertext: bytes,
        key_version: int,
    ) -> str:
        if key_version != self.key_version:
            raise ValueError(f"key version {key_version} is not loaded")
        nonce, encrypted = ciphertext[:NONCE_SIZE], ciphertext[NONCE_SIZE:]
        plaintext = self._cipher.decrypt(
            nonce,
            encrypted,
            self._context_aad(context, field_name, key_version),
        )
        return plaintext.decode("utf-8")

    def encrypt(self, account_id: uuid.UUID, field_name: str, value: str) -> EncryptedValue:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._cipher.encrypt(
            nonce,
            value.encode("utf-8"),
            self._aad(account_id, field_name, self.key_version),
        )
        return EncryptedValue(nonce + ciphertext, self.key_version)

    def decrypt(
        self,
        account_id: uuid.UUID,
        field_name: str,
        ciphertext: bytes,
        key_version: int,
    ) -> str:
        if key_version != self.key_version:
            raise ValueError(f"key version {key_version} is not loaded")
        nonce, encrypted = ciphertext[:NONCE_SIZE], ciphertext[NONCE_SIZE:]
        plaintext = self._cipher.decrypt(
            nonce,
            encrypted,
            self._aad(account_id, field_name, key_version),
        )
        return plaintext.decode("utf-8")
