from __future__ import annotations
import pytest
from src.domain.ports import InvalidCredentialsError
from src.domain.services import ForgotPasswordService

pytestmark = pytest.mark.unit

@pytest.fixture
def service(auth):
    return ForgotPasswordService(auth=auth)

class TestStart:
    def test_delegado_al_auth_provider(self, service, auth):
        service.start("alice@example.com")
        assert ("start_forgot_password", {"email": "alice@example.com"}) in auth.calls

    def test_rechaza_email_vacio(self, service, auth):
        with pytest.raises(InvalidCredentialsError):
            service.start("")
        assert auth.calls == []

class TestConfirm:
    def test_delegado_al_auth_provider(self, service, auth):
        service.confirm("alice@example.com", "123456", "NewPass1!")
        assert auth.calls[-1] == (
            "confirm_forgot_password",
            {
                "email": "alice@example.com",
                "code": "123456",
                "new_password": "NewPass1!",
            },
        )

    @pytest.mark.parametrize(
        "email,code,new_password",
        [
            ("", "123", "x"),
            ("a@b.com", "", "x"),
            ("a@b.com", "123", ""),
            (None, "123", "x"),
        ],
    )
    def test_rechaza_campos_obligatorios_vacios(
        self, service, auth, email, code, new_password
    ):
        with pytest.raises(InvalidCredentialsError):
            service.confirm(email, code, new_password)
        assert auth.calls == []
