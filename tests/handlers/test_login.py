from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import (
    AuthTokens,
    InvalidCredentialsError,
    NewPasswordRequiredError,
    TooManyAttemptsError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import LoginResult
from src.domain.user import User

pytestmark = pytest.mark.unit


def _event(body: dict | str | None = "default") -> dict:
    if body == "default":
        body = {"email": "alice@example.com", "password": "Secret123!"}
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


def _user() -> User:
    return User.new(
        cognito_sub="sub-1",
        email="alice@example.com",
        full_name="Alice",
        role="EJEC",
    )


@pytest.fixture
def login_module(monkeypatch):
    from src.handlers import login as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


class TestLoginHandler:
    def test_success_returns_tokens_and_user(self, login_module):
        tokens = AuthTokens("id", "acc", "ref", 3600, "Bearer")
        user = _user()
        login_module._service.login.return_value = LoginResult(tokens=tokens, user=user)

        resp = login_module.handler(_event(), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["tokens"]["id_token"] == "id"
        assert body["user"]["email"] == "alice@example.com"

    def test_invalid_body_returns_400(self, login_module):
        resp = login_module.handler(_event("{not json"), None)
        assert resp["statusCode"] == 400

    def test_too_many_attempts_returns_429(self, login_module):
        login_module._service.login.side_effect = TooManyAttemptsError(retry_after_seconds=60)
        resp = login_module.handler(_event(), None)
        assert resp["statusCode"] == 429
        assert resp["headers"]["Retry-After"] == "60"
        assert json.loads(resp["body"])["retry_after"] == 60

    def test_new_password_required_returns_200_with_challenge(self, login_module):
        login_module._service.login.side_effect = NewPasswordRequiredError(
            session="sess-1", email="alice@example.com"
        )
        resp = login_module.handler(_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["challenge"] == "NEW_PASSWORD_REQUIRED"
        assert body["session"] == "sess-1"

    def test_invalid_credentials_returns_401(self, login_module):
        login_module._service.login.side_effect = InvalidCredentialsError("bad")
        resp = login_module.handler(_event(), None)
        assert resp["statusCode"] == 401

    def test_user_disabled_returns_403(self, login_module):
        login_module._service.login.side_effect = UserDisabledError("disabled")
        resp = login_module.handler(_event(), None)
        assert resp["statusCode"] == 403

    def test_user_not_found_returns_404(self, login_module):
        login_module._service.login.side_effect = UserNotFoundError("missing")
        resp = login_module.handler(_event(), None)
        assert resp["statusCode"] == 404
