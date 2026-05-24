from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.user import User

pytestmark = pytest.mark.unit


def _event(qs: dict | None = None, admin: bool = True) -> dict:
    groups = ["ADMIN"] if admin else ["EJEC"]
    return {
        "queryStringParameters": qs,
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"cognito:groups": groups}}}
        },
    }


@pytest.fixture
def list_users_module(monkeypatch):
    from src.handlers import list_users as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


class TestListUsersHandler:
    def test_success_returns_200_with_users(self, list_users_module):
        user = User.new("s1", "a@example.com", "A", "EJEC")
        list_users_module._service.list.return_value = [user]
        resp = list_users_module.handler(_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["count"] == 1

    def test_uses_default_limit_when_qs_invalid(self, list_users_module):
        list_users_module._service.list.return_value = []
        resp = list_users_module.handler(_event({"limit": "abc"}), None)
        assert resp["statusCode"] == 200
        list_users_module._service.list.assert_called_with(limit=50)

    def test_respects_custom_limit(self, list_users_module):
        list_users_module._service.list.return_value = []
        list_users_module.handler(_event({"limit": "10"}), None)
        list_users_module._service.list.assert_called_with(limit=10)

    def test_caps_limit_at_1000(self, list_users_module):
        list_users_module._service.list.return_value = []
        list_users_module.handler(_event({"limit": "9999"}), None)
        list_users_module._service.list.assert_called_with(limit=1000)

    def test_non_admin_returns_403(self, list_users_module):
        resp = list_users_module.handler(_event(admin=False), None)
        assert resp["statusCode"] == 403
