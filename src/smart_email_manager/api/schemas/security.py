from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr


class MasterKeyRotationRequest(BaseModel):
    old_master_key: SecretStr
    old_key_version: int = Field(ge=1)
    commit: bool = False


class MasterKeyRotationResult(BaseModel):
    committed: bool
    old_key_version: int
    new_key_version: int
    account_secrets: int
    import_items: int
    proxy_profiles: int
    forwarding_destinations: int
