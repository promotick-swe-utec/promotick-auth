"""Tests del StrictEmailValidator.

Importante: DNS apagado por defecto en estos tests (`check_dns=False`) — la
red no es una dependencia de tests unitarios. Hay un solo test que mockea
socket para verificar el branch DNS.
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from src.adapters.strict_email_validator import StrictEmailValidator
from src.domain.user import InvalidEmailError


pytestmark = pytest.mark.unit


@pytest.fixture
def validator() -> StrictEmailValidator:
    return StrictEmailValidator(check_dns=False)


class TestFormato:
    def test_acepta_email_valido(self, validator):
        validator.validate("user@example.com")

    @pytest.mark.parametrize(
        "email",
        [
            "",
            "no-arroba",
            "@example.com",
            "user@",
            "user@.com",
            "user@example..com",
            "a..b@example.com",
        ],
    )
    def test_rechaza_formatos_invalidos(self, validator, email):
        with pytest.raises(InvalidEmailError):
            validator.validate(email)

    def test_rechaza_email_demasiado_largo(self, validator):
        with pytest.raises(InvalidEmailError, match="demasiado largo"):
            validator.validate("a" * 250 + "@example.com")

    def test_rechaza_local_part_mayor_a_64(self, validator):
        with pytest.raises(InvalidEmailError, match="64 caracteres"):
            validator.validate("a" * 65 + "@example.com")

    def test_normaliza_antes_de_validar(self, validator):
        validator.validate("  USER@Example.COM  ")


class TestDominiosDesechables:
    @pytest.mark.parametrize(
        "domain",
        ["mailinator.com", "yopmail.com", "10minutemail.com", "trashmail.com"],
    )
    def test_rechaza_dominio_desechable(self, validator, domain):
        with pytest.raises(InvalidEmailError, match="desechables"):
            validator.validate(f"alguien@{domain}")


class TestTypos:
    @pytest.mark.parametrize(
        "wrong,suggested",
        [
            ("gmial.com", "gmail.com"),
            ("hotnail.com", "hotmail.com"),
            ("yaho.com", "yahoo.com"),
            ("outlok.com", "outlook.com"),
        ],
    )
    def test_sugiere_correccion_para_typos(self, validator, wrong, suggested):
        with pytest.raises(InvalidEmailError) as exc:
            validator.validate(f"user@{wrong}")
        assert suggested in str(exc.value)


class TestDns:
    def test_acepta_cuando_dns_resuelve(self):
        v = StrictEmailValidator(check_dns=True)
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            v.validate("user@example.com")

    def test_rechaza_cuando_dns_no_resuelve(self):
        v = StrictEmailValidator(check_dns=True)
        with patch("socket.gethostbyname", side_effect=socket.gaierror):
            with pytest.raises(InvalidEmailError, match="no existe"):
                v.validate("user@no-such-domain.invalid")

    def test_acepta_si_dns_falla_por_otro_motivo(self):
        """Errores transitorios (timeouts, etc.) NO deben bloquear al usuario."""
        v = StrictEmailValidator(check_dns=True)
        with patch("socket.gethostbyname", side_effect=OSError("network down")):
            v.validate("user@example.com")
