from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import UserAlreadyExistsError
from src.domain.user import InvalidEmailError, InvalidRoleError, User

pytestmark = pytest.mark.unit


def _admin_event(body: dict | str | None = None) -> dict:
    return {
        "body": json.dumps(body) if isinstance(body, dict) else body,
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"cognito:groups": ["ADMIN"]}}}
        },
    }


def _non_admin_event(body: dict) -> dict:
    return {
        "body": json.dumps(body),
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"cognito:groups": ["EJEC"]}}}
        },
    }


def _user(role: str = "EJEC") -> User:
    return User.new(
        cognito_sub="sub-1", email="x@example.com", full_name="X", role=role
    )


@pytest.fixture
def create_user_module(monkeypatch):
    from src.handlers import create_user as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


class TestCreateUserHandler:
    def test_success_returns_201(self, create_user_module):
        create_user_module._service.create.return_value = _user()
        body = {"email": "x@example.com", "full_name": "X", "role": "EJEC"}
        resp = create_user_module.handler(_admin_event(body), None)
        assert resp["statusCode"] == 201

    def test_missing_required_field_returns_400(self, create_user_module):
        body = {"email": "x@example.com"}
        resp = create_user_module.handler(_admin_event(body), None)
        assert resp["statusCode"] == 400
        assert "role" in json.loads(resp["body"])["error"]

    def test_invalid_email_returns_400(self, create_user_module):
        create_user_module._service.create.side_effect = InvalidEmailError("bad email")
        body = {"email": "bad", "full_name": "X", "role": "EJEC"}
        resp = create_user_module.handler(_admin_event(body), None)
        assert resp["statusCode"] == 400

    def test_invalid_role_returns_400(self, create_user_module):
        create_user_module._service.create.side_effect = InvalidRoleError("bad role")
        body = {"email": "x@example.com", "full_name": "X", "role": "WHAT"}
        resp = create_user_module.handler(_admin_event(body), None)
        assert resp["statusCode"] == 400

    def test_non_admin_returns_403(self, create_user_module):
        body = {"email": "x@example.com", "full_name": "X", "role": "EJEC"}
        resp = create_user_module.handler(_non_admin_event(body), None)
        assert resp["statusCode"] == 403

    def test_duplicate_returns_409(self, create_user_module):
        create_user_module._service.create.side_effect = UserAlreadyExistsError("dup")
        body = {"email": "x@example.com", "full_name": "X", "role": "EJEC"}
        resp = create_user_module.handler(_admin_event(body), None)
        assert resp["statusCode"] == 409
