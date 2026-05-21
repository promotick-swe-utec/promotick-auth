from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import UserNotFoundError
from src.domain.user import InvalidRoleError, User

pytestmark = pytest.mark.unit


def _event(
    body: dict | str | None = None,
    user_id: str = "uid-1",
    admin: bool = True,
) -> dict:
    groups = ["ADMIN"] if admin else ["EJEC"]
    return {
        "body": json.dumps(body) if isinstance(body, dict) else body,
        "pathParameters": {"user_id": user_id} if user_id else {},
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"cognito:groups": groups, "sub": "actor-1"}}}
        },
    }


def _user() -> User:
    return User.new("s1", "a@example.com", "A", "EJEC")


@pytest.fixture
def update_user_module(monkeypatch):
    from src.handlers import update_user as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


class TestUpdateUserHandler:
    def test_success_returns_200(self, update_user_module):
        update_user_module._service.update.return_value = _user()
        resp = update_user_module.handler(_event({"full_name": "Z"}), None)
        assert resp["statusCode"] == 200

    def test_missing_user_id_returns_400(self, update_user_module):
        resp = update_user_module.handler(_event({"full_name": "Z"}, user_id=""), None)
        assert resp["statusCode"] == 400

    def test_is_active_as_string_returns_400(self, update_user_module):
        resp = update_user_module.handler(_event({"is_active": "true"}), None)
        assert resp["statusCode"] == 400

    def test_invalid_role_returns_400(self, update_user_module):
        update_user_module._service.update.side_effect = InvalidRoleError("bad role")
        resp = update_user_module.handler(_event({"role": "BAD"}), None)
        assert resp["statusCode"] == 400

    def test_non_admin_returns_403(self, update_user_module):
        resp = update_user_module.handler(
            _event({"full_name": "Z"}, admin=False), None
        )
        assert resp["statusCode"] == 403

    def test_permission_error_returns_403(self, update_user_module):
        update_user_module._service.update.side_effect = PermissionError("nope")
        resp = update_user_module.handler(_event({"is_active": False}), None)
        assert resp["statusCode"] == 403

    def test_user_not_found_returns_404(self, update_user_module):
        update_user_module._service.update.side_effect = UserNotFoundError("missing")
        resp = update_user_module.handler(_event({"full_name": "Z"}), None)
        assert resp["statusCode"] == 404
