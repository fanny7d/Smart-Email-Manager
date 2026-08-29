from __future__ import annotations

import base64
import binascii

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.security import (
    MasterKeyRotationRequest,
    MasterKeyRotationResult,
)
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    AccountSecret,
    ForwardingDestination,
    ImportBatchItem,
    ProxyProfile,
)
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.audit import add_audit_log


def _decode_old_cipher(payload: MasterKeyRotationRequest) -> AccountSecretCipher:
    try:
        key = base64.b64decode(
            payload.old_master_key.get_secret_value().encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ApiProblem(
            status=422,
            code="OLD_MASTER_KEY_INVALID",
            title="Old master key is invalid",
            detail="old_master_key must be URL-safe base64 for exactly 32 bytes.",
        ) from exc
    if len(key) != 32:
        raise ApiProblem(
            status=422,
            code="OLD_MASTER_KEY_INVALID",
            title="Old master key is invalid",
            detail="old_master_key must decode to exactly 32 bytes.",
        )
    return AccountSecretCipher(key, payload.old_key_version)


def _rotate_context_field(
    old: AccountSecretCipher,
    new: AccountSecretCipher,
    *,
    context: str,
    field_name: str,
    ciphertext: bytes | None,
) -> bytes | None:
    if not ciphertext:
        return None
    plaintext = old.decrypt_context(context, field_name, ciphertext, old.key_version)
    return new.encrypt_context(context, field_name, plaintext).ciphertext


async def rotate_master_key(
    session: AsyncSession,
    payload: MasterKeyRotationRequest,
) -> MasterKeyRotationResult:
    old = _decode_old_cipher(payload)
    new = AccountSecretCipher.from_settings(get_settings())
    if new.key_version <= old.key_version:
        raise ApiProblem(
            status=409,
            code="MASTER_KEY_VERSION_NOT_INCREMENTED",
            title="Master key version was not incremented",
            detail="Set SEM_MASTER_KEY_VERSION to a value greater than old_key_version.",
        )
    account_rows = list(
        (
            await session.scalars(
                select(AccountSecret).where(AccountSecret.key_version == old.key_version).with_for_update()
            )
        ).all()
    )
    import_rows = list(
        (
            await session.scalars(
                select(ImportBatchItem)
                .where(ImportBatchItem.key_version == old.key_version)
                .with_for_update()
            )
        ).all()
    )
    proxy_rows = list(
        (
            await session.scalars(
                select(ProxyProfile).where(ProxyProfile.key_version == old.key_version).with_for_update()
            )
        ).all()
    )
    forwarding_rows = list(
        (
            await session.scalars(
                select(ForwardingDestination)
                .where(ForwardingDestination.key_version == old.key_version)
                .with_for_update()
            )
        ).all()
    )
    result = MasterKeyRotationResult(
        committed=payload.commit,
        old_key_version=old.key_version,
        new_key_version=new.key_version,
        account_secrets=len(account_rows),
        import_items=len(import_rows),
        proxy_profiles=len(proxy_rows),
        forwarding_destinations=len(forwarding_rows),
    )
    if not payload.commit:
        await session.rollback()
        return result

    for account_secret in account_rows:
        for field_name in ("password", "refresh_token"):
            ciphertext = getattr(account_secret, f"{field_name}_ciphertext")
            if ciphertext:
                plaintext = old.decrypt(
                    account_secret.account_id,
                    field_name,
                    ciphertext,
                    old.key_version,
                )
                setattr(
                    account_secret,
                    f"{field_name}_ciphertext",
                    new.encrypt(account_secret.account_id, field_name, plaintext).ciphertext,
                )
        account_secret.key_version = new.key_version
    for import_item in import_rows:
        context = f"import:{import_item.batch_id}:line:{import_item.line_number}"
        for field_name in ("password", "refresh_token"):
            setattr(
                import_item,
                f"{field_name}_ciphertext",
                _rotate_context_field(
                    old,
                    new,
                    context=context,
                    field_name=field_name,
                    ciphertext=getattr(import_item, f"{field_name}_ciphertext"),
                ),
            )
        import_item.key_version = new.key_version
    for proxy_profile in proxy_rows:
        context = f"proxy:{proxy_profile.id}"
        for field_name in ("primary_url", "fallback_url_1", "fallback_url_2"):
            setattr(
                proxy_profile,
                f"{field_name}_ciphertext",
                _rotate_context_field(
                    old,
                    new,
                    context=context,
                    field_name=field_name,
                    ciphertext=getattr(proxy_profile, f"{field_name}_ciphertext"),
                ),
            )
        proxy_profile.key_version = new.key_version
    for forwarding_destination in forwarding_rows:
        forwarding_destination.secret_ciphertext = (
            _rotate_context_field(
                old,
                new,
                context=f"forwarding:{forwarding_destination.id}",
                field_name="secret",
                ciphertext=forwarding_destination.secret_ciphertext,
            )
            or b""
        )
        forwarding_destination.key_version = new.key_version
    add_audit_log(
        session,
        action="security.master_key_rotate",
        resource_type="master_key",
        resource_id=str(new.key_version),
        data=result.model_dump(exclude={"committed"}),
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result
