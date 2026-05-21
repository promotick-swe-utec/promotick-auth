"""Tests de los helpers HTTP usados por todos los handlers."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import pytest

from src.shared.http import claims, json_response, parse_body, require_admin


pytestmark = pytest.mark.unit


class TestJsonResponse:
    def test_status_y_body(self):
        resp = json_response(201, {"ok": True})
        assert resp["statusCode"] == 201
        assert json.loads(resp["body"]) == {"ok": True}

    def test_content_type_por_defecto(self):
        resp = json_response(200, {})
        assert resp["headers"]["Content-Type"] == "application/json"

    def test_headers_extra_se_mergean(self):
        resp = json_response(200, {}, headers={"x-trace-id": "abc"})
        assert resp["headers"]["x-trace-id"] == "abc"
        assert resp["headers"]["Content-Type"] == "application/json"

    def test_serializa_dataclass(self):
        @dataclass
        class Foo:
            a: int
            b: str

        resp = json_response(200, Foo(1, "x"))
        assert json.loads(resp["body"]) == {"a": 1, "b": "x"}

    def test_preserva_unicode(self):
        resp = json_response(200, {"msg": "código inválido"})
        # ensure_ascii=False ⇒ los caracteres latinos no se escapan
        assert "código" in resp["body"]


class TestParseBody:
    def test_json_normal(self):
        assert parse_body({"body": '{"a": 1}'}) == {"a": 1}

    def test_body_vacio_devuelve_dict_vacio(self):
        assert parse_body({"body": ""}) == {}
        assert parse_body({}) == {}
        assert parse_body({"body": None}) == {}

    def test_base64(self):
        encoded = base64.b64encode(b'{"x": 9}').decode()
        assert parse_body({"body": encoded, "isBase64Encoded": True}) == {"x": 9}

    def test_json_invalido_lanza_value_error(self):
        with pytest.raises(ValueError, match="JSON inválido"):
            parse_body({"body": "{not json"})


class TestClaims:
    def test_extrae_de_jwt_authorizer(self):
        event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "abc", "email": "x@y.z"}}}
            }
        }
        assert claims(event) == {"sub": "abc", "email": "x@y.z"}

    def test_fallback_a_authorizer_claims(self):
        event = {"requestContext": {"authorizer": {"claims": {"sub": "abc"}}}}
        assert claims(event) == {"sub": "abc"}

    def test_devuelve_dict_vacio_si_no_hay_auth(self):
        assert claims({}) == {}
        assert claims({"requestContext": {}}) == {}


class TestRequireAdmin:
    def _event(self, groups) -> dict:
        return {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"cognito:groups": groups}}}
            }
        }

    def test_acepta_admin_como_lista(self):
        require_admin(self._event(["ADMIN"]))  # no lanza

    def test_acepta_admin_como_string(self):
        require_admin(self._event("ADMIN"))

    def test_acepta_admin_como_string_con_brackets(self):
        # Cognito a veces serializa los grupos como "[ADMIN]" en el claim.
        require_admin(self._event("[ADMIN]"))

    def test_acepta_admin_entre_varios_grupos(self):
        require_admin(self._event(["VIEWER", "ADMIN"]))

    def test_rechaza_si_falta_admin(self):
        with pytest.raises(PermissionError):
            require_admin(self._event(["EJEC"]))

    def test_rechaza_si_no_hay_groups(self):
        with pytest.raises(PermissionError):
            require_admin({"requestContext": {"authorizer": {"jwt": {"claims": {}}}}})

    def test_fallback_a_custom_role(self):
        event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"custom:role": "ADMIN"}}}
            }
        }
        require_admin(event)
