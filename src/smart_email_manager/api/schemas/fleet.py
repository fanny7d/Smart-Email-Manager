from pydantic import BaseModel, Field


class StatusCount(BaseModel):
    status: str
    count: int = Field(ge=0)


class FleetSummary(BaseModel):
    total_accounts: int = Field(ge=0)
    active_accounts: int = Field(ge=0)
    needs_attention: int = Field(ge=0)
    lifecycle: list[StatusCount]
    authorization: list[StatusCount]
    token: list[StatusCount]
    mail_health: list[StatusCount]
    proxy_health: list[StatusCount]
