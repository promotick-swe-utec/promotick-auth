from __future__ import annotations

import pytest

from src.domain.ports import UserAlreadyExistsError
from src.domain.services import CreateUserService
from src.domain.user import InvalidEmailError, InvalidRoleError


pytestmark = pytest.mark.unit


@pytest.fixture
def service(repo, auth, email_validator):
    return CreateUserService(repo=repo, auth=auth, email_validator=email_validator)


class TestCreateExitoso:
    def test_crea_usuario_y_lo_persiste(self, service, repo, auth):
        auth.next_sub = "sub-xyz"
        user = service.create(
            email="new@example.com", full_name="New User", role="EJEC"
        )
        assert user.email == "new@example.com"
        assert user.cognito_sub == "sub-xyz"
        assert user.role == "EJEC"
        assert repo.get_by_id(user.user_id) == user

    def test_orden_de_operaciones(self, service, auth, email_validator):
        service.create(email="ok@example.com", full_name="x", role="VIEWER")
        assert email_validator.calls == ["ok@example.com"]
        assert auth.calls[0][0] == "admin_create_user"


class TestCreateValidaciones:
    def test_rechaza_rol_invalido_antes_de_tocar_validator(
        self, service, email_validator, auth
    ):
        with pytest.raises(InvalidRoleError):
            service.create(email="x@example.com", full_name="x", role="SUPERVISOR")
        assert email_validator.calls == []
        assert auth.calls == []

    def test_rechaza_email_invalido_y_no_llama_a_cognito(
        self, service, email_validator, auth
    ):
        email_validator.error = InvalidEmailError("formato malo")
        with pytest.raises(InvalidEmailError):
            service.create(email="bad", full_name="x", role="EJEC")
        assert auth.calls == []


class TestCreateUnicidad:
    def test_falla_si_el_email_ya_existe(self, service, repo, auth, make_user):
        repo.seed(make_user(email="dup@example.com"))
        with pytest.raises(UserAlreadyExistsError):
            service.create(email="dup@example.com", full_name="x", role="EJEC")
        assert auth.calls == []

    def test_falla_si_save_if_absent_devuelve_false(
        self, service, repo, auth, monkeypatch
    ):
        monkeypatch.setattr(repo, "save_if_absent", lambda u: False)
        with pytest.raises(UserAlreadyExistsError):
            service.create(email="race@example.com", full_name="x", role="EJEC")
