from __future__ import annotations
import pytest
from src.domain.ports import (
    InvalidCredentialsError,
    TooManyAttemptsError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import LoginService

pytestmark = pytest.mark.unit

@pytest.fixture
def service(repo, auth, rate_limiter):
    return LoginService(repo=repo, auth=auth, rate_limiter=rate_limiter)


class TestLoginExitoso:
    def test_devuelve_tokens_y_perfil(self, service, repo, auth, make_user):
        user = repo.seed(make_user(email="alice@example.com"))
        result = service.login("alice@example.com", "Pass1234")
        assert result.user == user
        assert result.tokens == auth.tokens

    def test_busca_perfil_por_email_normalizado(self, service, repo, make_user):
        repo.seed(make_user(email="alice@example.com"))
        result = service.login("  Alice@EXAMPLE.com ", "x")
        assert result.user.email == "alice@example.com"

    def test_consulta_al_rate_limiter_antes_de_cognito(
        self, service, repo, auth, rate_limiter, make_user
    ):
        repo.seed(make_user(email="alice@example.com"))
        service.login("alice@example.com", "x")
        assert rate_limiter.calls == ["alice@example.com"]
        assert any(c[0] == "authenticate" for c in auth.calls)

class TestLoginValidaciones:
    @pytest.mark.parametrize(
        "email,password",
        [("", "x"), ("user@example.com", ""), ("", ""), (None, "x"), ("x", None)],
    )
    def test_rechaza_email_o_password_vacios(self, service, email, password):
        with pytest.raises(InvalidCredentialsError):
            service.login(email, password)

    def test_no_llama_a_cognito_si_faltan_credenciales(self, service, auth):
        with pytest.raises(InvalidCredentialsError):
            service.login("", "")
        assert auth.calls == []


class TestLoginRateLimiting:
    def test_propaga_too_many_attempts(self, service, auth, rate_limiter):
        rate_limiter.error = TooManyAttemptsError(retry_after_seconds=42)
        with pytest.raises(TooManyAttemptsError) as exc:
            service.login("alice@example.com", "x")
        assert exc.value.retry_after_seconds == 42
        # No debe haber tocado Cognito.
        assert auth.calls == []


class TestLoginErrores:
    def test_si_cognito_rechaza_propaga_invalid_credentials(self, service, auth):
        auth.authenticate_error = InvalidCredentialsError("bad")
        with pytest.raises(InvalidCredentialsError):
            service.login("alice@example.com", "wrong")

    def test_falla_si_no_hay_perfil_en_dynamo(self, service, auth):
        # auth ok, pero el repo está vacío
        with pytest.raises(UserNotFoundError):
            service.login("ghost@example.com", "x")

    def test_falla_si_usuario_esta_inactivo(self, service, repo, make_user):
        user = make_user(email="alice@example.com").with_changes(is_active=False)
        repo.seed(user)
        with pytest.raises(UserDisabledError):
            service.login("alice@example.com", "x")
