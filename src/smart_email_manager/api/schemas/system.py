from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SystemHealth(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    service: str = "smart-email-manager-api"
    version: str
    checked_at: datetime
