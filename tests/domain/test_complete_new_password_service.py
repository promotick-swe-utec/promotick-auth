from __future__ import annotations
import pytest
from src.domain.ports import (
    InvalidCredentialsError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import CompleteNewPasswordService

pytestmark = pytest.mark.unit

@pytest.fixture
def service(repo, auth):
    return CompleteNewPasswordService(repo=repo, auth=auth)

class TestComplete:
    def test_devuelve_tokens_y_perfil_cuando_todo_ok(
        self, service, repo, auth, make_user
    ):
        user = repo.seed(make_user(email="user@example.com"))
        result = service.complete(
            email="user@example.com",
            new_password="NewPass1!",
            session="sess-xyz",
        )
        assert result.user == user
        assert result.tokens == auth.tokens
        assert auth.calls[-1][0] == "respond_new_password_challenge"

    @pytest.mark.parametrize(
        "email,new_password,session",
        [
            ("", "p", "s"),
            ("a@b.com", "", "s"),
            ("a@b.com", "p", ""),
        ],
    )
    def test_rechaza_campos_obligatorios_vacios(
        self, service, auth, email, new_password, session
    ):
        with pytest.raises(InvalidCredentialsError):
            service.complete(email=email, new_password=new_password, session=session)
        assert auth.calls == []

    def test_falla_si_no_existe_perfil_en_dynamo(self, service):
        with pytest.raises(UserNotFoundError):
            service.complete(
                email="ghost@example.com",
                new_password="NewPass1!",
                session="s",
            )

    def test_falla_si_usuario_inactivo(self, service, repo, make_user):
        repo.seed(make_user(email="user@example.com").with_changes(is_active=False))
        with pytest.raises(UserDisabledError):
            service.complete(
                email="user@example.com",
                new_password="NewPass1!",
                session="s",
            )
