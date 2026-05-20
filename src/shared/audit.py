import os
from typing import Optional

from src.adapters.dynamo_audit_log_repository import DynamoAuditLogRepository
from src.shared.http import claims


_repo = DynamoAuditLogRepository(table_name=os.environ["AUDIT_LOGS_TABLE_NAME"])


def _request_context(event: dict) -> dict:
    rc = event.get("requestContext") or {}
    http = rc.get("http") or {}
    headers = event.get("headers") or {}
    return {
        "ip": http.get("sourceIp") or headers.get("x-forwarded-for"),
        "user_agent": http.get("userAgent") or headers.get("user-agent"),
        "http_method": http.get("method"),
        "path": http.get("path") or rc.get("path"),
    }


def audit_log(
    event: dict,
    event_type: str,
    status: str,
    target_key: str,
    status_code: Optional[int] = None,
    metadata: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    c = claims(event)
    actor_id = c.get("custom:user_id") or c.get("sub")
    actor_email = c.get("email")
    _repo.log(
        event_type=event_type,
        status=status,
        target_key=target_key,
        actor_id=actor_id,
        actor_email=actor_email,
        status_code=status_code,
        metadata=metadata,
        error=error,
        **_request_context(event),
    )


def email_target(email: Optional[str]) -> str:
    e = (email or "").strip().lower()
    return f"email#{e}" if e else "email#unknown"


def user_target(user_id: Optional[str]) -> str:
    return f"user#{user_id}" if user_id else "user#unknown"
