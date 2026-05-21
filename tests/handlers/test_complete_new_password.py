from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import (
    AuthTokens,
    InvalidCredentialsError,
    InvalidPasswordError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import LoginResult
from src.domain.user import User

pytestmark = pytest.mark.unit


def _event(body: dict | str | None = None) -> dict:
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


def _user() -> User:
    return User.new("s1", "a@example.com", "A", "EJEC")


@pytest.fixture
def complete_module(monkeypatch):
    from src.handlers import complete_new_password as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


_BODY = {"email": "a@example.com", "new_password": "Strong-Pass-1!", "session": "sess-1"}


class TestCompleteNewPasswordHandler:
    def test_success_returns_200_with_tokens(self, complete_module):
        tokens = AuthTokens("id", "acc", "ref", 3600, "Bearer")
        complete_module._service.complete.return_value = LoginResult(
            tokens=tokens, user=_user()
        )
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["tokens"]["access_token"] == "acc"

    def test_value_error_returns_400(self, complete_module):
        complete_module._service.complete.side_effect = ValueError("bad")
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 400

    def test_invalid_password_returns_400(self, complete_module):
        complete_module._service.complete.side_effect = InvalidPasswordError("bad")
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 400

    def test_invalid_credentials_returns_401(self, complete_module):
        complete_module._service.complete.side_effect = InvalidCredentialsError("bad")
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 401

    def test_user_disabled_returns_403(self, complete_module):
        complete_module._service.complete.side_effect = UserDisabledError("disabled")
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 403

    def test_user_not_found_returns_404(self, complete_module):
        complete_module._service.complete.side_effect = UserNotFoundError("missing")
        resp = complete_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 404
