from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import (
    InvalidConfirmationCodeError,
    InvalidCredentialsError,
    InvalidPasswordError,
    UserNotFoundError,
)

pytestmark = pytest.mark.unit


def _event(body: dict | str | None = None) -> dict:
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


@pytest.fixture
def confirm_module(monkeypatch):
    from src.handlers import confirm_forgot_password as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


_BODY = {"email": "x@y.z", "code": "123456", "new_password": "Strong-Pass-1!"}


class TestConfirmForgotPasswordHandler:
    def test_success_returns_200(self, confirm_module):
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 200

    def test_value_error_returns_400(self, confirm_module):
        confirm_module._service.confirm.side_effect = ValueError("bad")
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 400

    def test_invalid_code_returns_400(self, confirm_module):
        confirm_module._service.confirm.side_effect = InvalidConfirmationCodeError("bad")
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 400

    def test_invalid_password_returns_400(self, confirm_module):
        confirm_module._service.confirm.side_effect = InvalidPasswordError("bad")
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 400

    def test_invalid_credentials_returns_401(self, confirm_module):
        confirm_module._service.confirm.side_effect = InvalidCredentialsError("bad")
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 401

    def test_user_not_found_returns_404(self, confirm_module):
        confirm_module._service.confirm.side_effect = UserNotFoundError("missing")
        resp = confirm_module.handler(_event(_BODY), None)
        assert resp["statusCode"] == 404
