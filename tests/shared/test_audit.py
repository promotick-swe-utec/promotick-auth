from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("AUDIT_LOGS_TABLE_NAME", "test-audit")

import boto3  # noqa: E402

_fake_table = MagicMock()
_fake_resource = MagicMock()
_fake_resource.Table.return_value = _fake_table
boto3.resource = lambda *a, **kw: _fake_resource  # type: ignore[assignment]

from src.shared import audit  # noqa: E402

pytestmark = pytest.mark.unit


class TestEmailTarget:
    def test_normalizes_email(self):
        assert audit.email_target("X@Y.Z") == "email#x@y.z"

    def test_none_returns_unknown(self):
        assert audit.email_target(None) == "email#unknown"

    def test_empty_returns_unknown(self):
        assert audit.email_target("   ") == "email#unknown"


class TestUserTarget:
    def test_with_id(self):
        assert audit.user_target("u-1") == "user#u-1"

    def test_none(self):
        assert audit.user_target(None) == "user#unknown"


class TestRequestContext:
    def test_extracts_from_http(self):
        event = {
            "requestContext": {
                "http": {
                    "sourceIp": "1.2.3.4",
                    "userAgent": "UA",
                    "method": "POST",
                    "path": "/x",
                }
            }
        }
        ctx = audit._request_context(event)
        assert ctx == {
            "ip": "1.2.3.4",
            "user_agent": "UA",
            "http_method": "POST",
            "path": "/x",
        }

    def test_falls_back_to_headers(self):
        event = {
            "headers": {"x-forwarded-for": "9.9.9.9", "user-agent": "alt-UA"},
            "requestContext": {"path": "/legacy"},
        }
        ctx = audit._request_context(event)
        assert ctx["ip"] == "9.9.9.9"
        assert ctx["user_agent"] == "alt-UA"
        assert ctx["path"] == "/legacy"

    def test_handles_empty_event(self):
        ctx = audit._request_context({})
        assert ctx == {"ip": None, "user_agent": None, "http_method": None, "path": None}


class TestAuditLog:
    def test_calls_repository_with_actor_and_context(self, monkeypatch):
        repo_mock = MagicMock()
        monkeypatch.setattr(audit, "_repo", repo_mock)
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "custom:user_id": "actor-1",
                            "email": "a@b.c",
                        }
                    }
                },
                "http": {"sourceIp": "1.1.1.1", "method": "POST", "path": "/x"},
            }
        }
        audit.audit_log(
            event,
            event_type="test.event",
            status="success",
            target_key="user#1",
            status_code=200,
            metadata={"k": "v"},
        )
        kwargs = repo_mock.log.call_args.kwargs
        assert kwargs["actor_id"] == "actor-1"
        assert kwargs["actor_email"] == "a@b.c"
        assert kwargs["ip"] == "1.1.1.1"

    def test_falls_back_to_sub_when_no_custom_user_id(self, monkeypatch):
        repo_mock = MagicMock()
        monkeypatch.setattr(audit, "_repo", repo_mock)
        event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "sub-1"}}}
            }
        }
        audit.audit_log(event, event_type="e", status="s", target_key="t")
        assert repo_mock.log.call_args.kwargs["actor_id"] == "sub-1"
