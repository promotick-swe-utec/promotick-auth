from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.domain.ports import InvalidCredentialsError

pytestmark = pytest.mark.unit


def _event(body: dict | str | None = None) -> dict:
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


@pytest.fixture
def forgot_module(monkeypatch):
    from src.handlers import forgot_password as mod

    monkeypatch.setattr(mod, "_service", MagicMock())
    monkeypatch.setattr(mod, "audit_log", MagicMock())
    return mod


class TestForgotPasswordHandler:
    def test_success_returns_200(self, forgot_module):
        resp = forgot_module.handler(_event({"email": "x@y.z"}), None)
        assert resp["statusCode"] == 200

    def test_invalid_json_returns_400(self, forgot_module):
        resp = forgot_module.handler(_event("{nope"), None)
        assert resp["statusCode"] == 400

    def test_service_value_error_returns_400(self, forgot_module):
        forgot_module._service.start.side_effect = ValueError("bad")
        resp = forgot_module.handler(_event({"email": "x@y.z"}), None)
        assert resp["statusCode"] == 400

    def test_invalid_credentials_returns_400(self, forgot_module):
        forgot_module._service.start.side_effect = InvalidCredentialsError("nope")
        resp = forgot_module.handler(_event({"email": "x@y.z"}), None)
        assert resp["statusCode"] == 400
