import logging
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

from src.domain.ports import TooManyAttemptsError


_logger = logging.getLogger(__name__)


class DynamoLoginRateLimiter:

    def __init__(
        self,
        table_name: str,
        max_attempts: int = 5,
        window_seconds: int = 60,
        block_seconds: int = 300,
        index_name: str = "by_target_created",
        resource=None,
    ):
        self._table = (resource or boto3.resource("dynamodb")).Table(table_name)
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._block_seconds = block_seconds
        self._index_name = index_name

    def check(self, email: str) -> None:
        e = (email or "").strip().lower()
        if not e:
            return
        target_key = f"email#{e}"
        now = datetime.now(timezone.utc)
        lookback_iso = self._iso(now - timedelta(seconds=self._block_seconds))

        try:
            resp = self._table.query(
                IndexName=self._index_name,
                KeyConditionExpression=(
                    Key("target_key").eq(target_key)
                    & Key("created_at").gte(lookback_iso)
                ),
                FilterExpression="event_type = :et AND #s = :st",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":et": "auth.login",
                    ":st": "failed",
                },
                ProjectionExpression="created_at",
            )
        except Exception as exc:
            # Fail-open: si Dynamo falla, no bloquear logins legítimos.
            _logger.warning("Rate limiter query falló: %s", exc)
            return

        items = resp.get("Items") or []
        if len(items) < self._max_attempts:
            return

        timestamps = sorted(self._parse(i["created_at"]) for i in items)

        n = self._max_attempts
        latest_trigger = None
        for i in range(len(timestamps) - n + 1):
            span = (timestamps[i + n - 1] - timestamps[i]).total_seconds()
            if span <= self._window_seconds:
                latest_trigger = timestamps[i + n - 1]

        if latest_trigger is None:
            return

        unblock_at = latest_trigger + timedelta(seconds=self._block_seconds)
        if now < unblock_at:
            retry_after = int((unblock_at - now).total_seconds()) + 1
            raise TooManyAttemptsError(retry_after_seconds=retry_after)

    @staticmethod
    def _iso(ts: datetime) -> str:
        return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _parse(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
