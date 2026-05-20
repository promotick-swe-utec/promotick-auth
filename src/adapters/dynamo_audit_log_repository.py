import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import boto3


_logger = logging.getLogger(__name__)


class DynamoAuditLogRepository:

    def __init__(
        self,
        table_name: str,
        retention_days: int = 365,
        resource=None,
    ):
        self._table = (resource or boto3.resource("dynamodb")).Table(table_name)
        self._retention_days = retention_days

    def log(
        self,
        event_type: str,
        status: str,
        target_key: str,
        actor_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        http_method: Optional[str] = None,
        path: Optional[str] = None,
        status_code: Optional[int] = None,
        metadata: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        item: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "target_key": target_key,
            "created_at": now.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "event_type": event_type,
            "status": status,
            "expires_at": int(
                (now + timedelta(days=self._retention_days)).timestamp()
            ),
        }
        if actor_id:
            item["actor_id"] = actor_id
        if actor_email:
            item["actor_email"] = actor_email
        if ip:
            item["ip"] = ip
        if user_agent:
            item["user_agent"] = user_agent
        if http_method:
            item["http_method"] = http_method
        if path:
            item["path"] = path
        if status_code is not None:
            item["status_code"] = int(status_code)
        if error:
            item["error"] = str(error)[:1000]
        if metadata:
            item["metadata"] = metadata

        try:
            self._table.put_item(Item=item)
        except Exception as exc:
            _logger.warning("No se pudo escribir audit log: %s", exc)
