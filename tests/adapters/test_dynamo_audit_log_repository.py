from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.adapters.dynamo_audit_log_repository import DynamoAuditLogRepository

pytestmark = pytest.mark.unit


def _resource(table: MagicMock) -> MagicMock:
    resource = MagicMock()
    resource.Table.return_value = table
    return resource


class TestDynamoAuditLogRepository:
    def test_log_minimal_payload(self):
        table = MagicMock()
        repo = DynamoAuditLogRepository("t", resource=_resource(table))
        repo.log(event_type="auth.login", status="success", target_key="user#1")
        table.put_item.assert_called_once()
        item = table.put_item.call_args.kwargs["Item"]
        assert item["event_type"] == "auth.login"
        assert item["target_key"] == "user#1"
        assert "event_id" in item
        assert "expires_at" in item

    def test_log_includes_optional_fields(self):
        table = MagicMock()
        repo = DynamoAuditLogRepository("t", resource=_resource(table))
        repo.log(
            event_type="user.created",
            status="success",
            target_key="user#1",
            actor_id="actor-1",
            actor_email="a@b.c",
            ip="1.2.3.4",
            user_agent="UA",
            http_method="POST",
            path="/users",
            status_code=201,
            metadata={"k": "v"},
            error="boom",
        )
        item = table.put_item.call_args.kwargs["Item"]
        assert item["actor_id"] == "actor-1"
        assert item["actor_email"] == "a@b.c"
        assert item["ip"] == "1.2.3.4"
        assert item["user_agent"] == "UA"
        assert item["http_method"] == "POST"
        assert item["path"] == "/users"
        assert item["status_code"] == 201
        assert item["metadata"] == {"k": "v"}
        assert item["error"] == "boom"

    def test_log_truncates_long_error(self):
        table = MagicMock()
        repo = DynamoAuditLogRepository("t", resource=_resource(table))
        repo.log(
            event_type="x",
            status="failed",
            target_key="user#1",
            error="x" * 2000,
        )
        item = table.put_item.call_args.kwargs["Item"]
        assert len(item["error"]) == 1000

    def test_log_swallows_put_item_errors(self):
        table = MagicMock()
        table.put_item.side_effect = Exception("dynamo down")
        repo = DynamoAuditLogRepository("t", resource=_resource(table))
        repo.log(event_type="x", status="failed", target_key="user#1")
