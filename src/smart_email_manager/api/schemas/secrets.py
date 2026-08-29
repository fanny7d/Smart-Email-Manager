from __future__ import annotations

import uuid

from pydantic import BaseModel, SecretStr, model_validator


class AccountSecretsWrite(BaseModel):
    password: SecretStr | None = None
    refresh_token: SecretStr | None = None

    @model_validator(mode="after")
    def require_one_field(self) -> AccountSecretsWrite:
        if self.password is None and self.refresh_token is None:
            raise ValueError("at least one secret field must be provided")
        return self


class AccountSecretsStatus(BaseModel):
    account_id: uuid.UUID
    has_password: bool
    has_refresh_token: bool
    key_version: int | None
