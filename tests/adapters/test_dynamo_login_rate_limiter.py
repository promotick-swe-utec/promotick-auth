from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.adapters.dynamo_login_rate_limiter import DynamoLoginRateLimiter
from src.domain.ports import TooManyAttemptsError

pytestmark = pytest.mark.unit


def _resource(table: MagicMock) -> MagicMock:
    resource = MagicMock()
    resource.Table.return_value = table
    return resource


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TestDynamoLoginRateLimiter:
    def test_empty_email_short_circuits(self):
        table = MagicMock()
        limiter = DynamoLoginRateLimiter("t", resource=_resource(table))
        limiter.check("")
        table.query.assert_not_called()

    def test_under_threshold_allows(self):
        table = MagicMock()
        table.query.return_value = {"Items": [{"created_at": _iso(datetime.now(timezone.utc))}]}
        limiter = DynamoLoginRateLimiter("t", max_attempts=5, resource=_resource(table))
        limiter.check("x@y.z")

    def test_over_threshold_within_window_blocks(self):
        now = datetime.now(timezone.utc)
        table = MagicMock()
        table.query.return_value = {
            "Items": [
                {"created_at": _iso(now - timedelta(seconds=i))} for i in range(5)
            ]
        }
        limiter = DynamoLoginRateLimiter(
            "t",
            max_attempts=5,
            window_seconds=60,
            block_seconds=300,
            resource=_resource(table),
        )
        with pytest.raises(TooManyAttemptsError) as exc:
            limiter.check("x@y.z")
        assert exc.value.retry_after_seconds > 0

    def test_spread_over_window_does_not_block(self):
        now = datetime.now(timezone.utc)
        table = MagicMock()
        table.query.return_value = {
            "Items": [
                {"created_at": _iso(now - timedelta(seconds=70 * i))} for i in range(5)
            ]
        }
        limiter = DynamoLoginRateLimiter(
            "t",
            max_attempts=5,
            window_seconds=60,
            block_seconds=300,
            resource=_resource(table),
        )
        limiter.check("x@y.z")

    def test_query_failure_fails_open(self):
        table = MagicMock()
        table.query.side_effect = Exception("dynamo down")
        limiter = DynamoLoginRateLimiter("t", resource=_resource(table))
        limiter.check("x@y.z")

    def test_no_items_allows(self):
        table = MagicMock()
        table.query.return_value = {"Items": []}
        limiter = DynamoLoginRateLimiter("t", resource=_resource(table))
        limiter.check("x@y.z")
