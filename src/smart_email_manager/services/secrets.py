from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.secrets import AccountSecretsStatus, AccountSecretsWrite
from smart_email_manager.db.models import Account, AccountSecret
from smart_email_manager.security.encryption import AccountSecretCipher


@dataclass(frozen=True)
class DecryptedAccountSecrets:
    password: str | None = None
    refresh_token: str | None = None


async def get_account_secret_row(session: AsyncSession, account_id: uuid.UUID) -> AccountSecret | None:
    if not await session.get(Account, account_id):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    return await session.get(AccountSecret, account_id)


def serialize_secret_status(account_id: uuid.UUID, row: AccountSecret | None) -> AccountSecretsStatus:
    return AccountSecretsStatus(
        account_id=account_id,
        has_password=bool(row and row.password_ciphertext),
        has_refresh_token=bool(row and row.refresh_token_ciphertext),
        key_version=row.key_version if row else None,
    )


async def get_account_secret_status(session: AsyncSession, account_id: uuid.UUID) -> AccountSecretsStatus:
    return serialize_secret_status(account_id, await get_account_secret_row(session, account_id))


async def write_account_secrets(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    payload: AccountSecretsWrite,
    cipher: AccountSecretCipher,
) -> AccountSecretsStatus:
    row = await get_account_secret_row(session, account_id)
    if row is None:
        row = AccountSecret(account_id=account_id, key_version=cipher.key_version)
        session.add(row)
    elif row.key_version != cipher.key_version:
        raise ApiProblem(
            status=409,
            code="SECRET_KEY_ROTATION_REQUIRED",
            title="Account secrets use another key version",
            detail="Rotate existing account secrets before writing with the active key.",
        )

    for field_name, column_name in (
        ("password", "password_ciphertext"),
        ("refresh_token", "refresh_token_ciphertext"),
    ):
        secret = getattr(payload, field_name)
        if secret is None:
            continue
        plaintext = secret.get_secret_value()
        encrypted = cipher.encrypt(account_id, field_name, plaintext) if plaintext else None
        setattr(row, column_name, encrypted.ciphertext if encrypted else None)

    row.key_version = cipher.key_version
    await session.commit()
    await session.refresh(row)
    return serialize_secret_status(account_id, row)


async def load_decrypted_account_secrets(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    cipher: AccountSecretCipher,
) -> DecryptedAccountSecrets:
    row = await get_account_secret_row(session, account_id)
    if row is None:
        return DecryptedAccountSecrets()

    def decrypt_field(field_name: str) -> str | None:
        ciphertext = getattr(row, f"{field_name}_ciphertext")
        if not ciphertext:
            return None
        return cipher.decrypt(account_id, field_name, ciphertext, row.key_version)

    return DecryptedAccountSecrets(
        password=decrypt_field("password"),
        refresh_token=decrypt_field("refresh_token"),
    )
