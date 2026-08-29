from enum import StrEnum


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class AuthorizationStatus(StrEnum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"


class TokenStatus(StrEnum):
    NEVER = "never"
    CHECKING = "checking"
    SUCCESS = "success"
    FAILED = "failed"
    STALE = "stale"


class MailHealthStatus(StrEnum):
    UNKNOWN = "unknown"
    CHECKING = "checking"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class ProxyHealthStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class JobItemStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
