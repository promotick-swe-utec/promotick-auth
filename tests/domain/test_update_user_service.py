from __future__ import annotations
import pytest
from src.domain.ports import UserNotFoundError
from src.domain.services import UpdateUserService
from src.domain.user import InvalidRoleError

pytestmark = pytest.mark.unit

@pytest.fixture
def service(repo, auth):
    return UpdateUserService(repo=repo, auth=auth)


class TestUpdateNotFound:
    def test_falla_si_user_id_no_existe(self, service):
        with pytest.raises(UserNotFoundError):
            service.update(
                user_id="missing", actor_user_id="anyone", full_name="X"
            )


class TestUpdateCamposBasicos:
    def test_actualiza_full_name(self, service, repo, make_user):
        u = repo.seed(make_user(full_name="Original"))
        result = service.update(
            user_id=u.user_id, actor_user_id="admin", full_name="Nuevo"
        )
        assert result.full_name == "Nuevo"
        assert repo.get_by_id(u.user_id).full_name == "Nuevo"

    def test_actualiza_role_y_sincroniza_con_cognito(
        self, service, repo, auth, make_user
    ):
        u = repo.seed(make_user(role="EJEC", email="x@example.com"))
        service.update(
            user_id=u.user_id, actor_user_id="admin", role="VIEWER"
        )
        assert (
            "set_user_role",
            {"email": "x@example.com", "old_role": "EJEC", "new_role": "VIEWER"},
        ) in auth.calls

    def test_no_sincroniza_cognito_si_role_no_cambio(
        self, service, repo, auth, make_user
    ):
        u = repo.seed(make_user(role="EJEC"))
        service.update(user_id=u.user_id, actor_user_id="admin", role="EJEC")
        assert not any(c[0] == "set_user_role" for c in auth.calls)

    def test_rechaza_role_invalido(self, service, repo, make_user):
        u = repo.seed(make_user())
        with pytest.raises(InvalidRoleError):
            service.update(user_id=u.user_id, actor_user_id="admin", role="HACKER")


class TestUpdateIsActive:
    def test_desactiva_y_sincroniza_con_cognito(
        self, service, repo, auth, make_user
    ):
        u = repo.seed(make_user(email="x@example.com"))
        result = service.update(
            user_id=u.user_id, actor_user_id="admin", is_active=False
        )
        assert result.is_active is False
        assert (
            "set_user_enabled",
            {"email": "x@example.com", "enabled": False},
        ) in auth.calls

    def test_no_toca_cognito_si_is_active_no_cambia(
        self, service, repo, auth, make_user
    ):
        u = repo.seed(make_user())  # is_active=True
        service.update(user_id=u.user_id, actor_user_id="admin", is_active=True)
        assert not any(c[0] == "set_user_enabled" for c in auth.calls)


class TestAutoBloqueoAdmin:

    def test_admin_no_puede_autodesactivarse(self, service, repo, auth, make_user):
        admin = repo.seed(make_user(role="ADMIN", email="admin@example.com"))
        with pytest.raises(PermissionError):
            service.update(
                user_id=admin.user_id,
                actor_user_id=admin.user_id,
                is_active=False,
            )
        # Nada se persistió ni se sincronizó con Cognito.
        assert repo.get_by_id(admin.user_id).is_active is True
        assert not any(c[0] == "set_user_enabled" for c in auth.calls)

    def test_admin_puede_desactivar_a_otro_admin(self, service, repo, make_user):
        other_admin = repo.seed(
            make_user(role="ADMIN", email="otro@example.com", cognito_sub="s2")
        )
        result = service.update(
            user_id=other_admin.user_id,
            actor_user_id="me-admin-id",
            is_active=False,
        )
        assert result.is_active is False

    def test_admin_puede_autoactualizar_nombre_y_rol(
        self, service, repo, make_user
    ):
        admin = repo.seed(make_user(role="ADMIN"))
        result = service.update(
            user_id=admin.user_id,
            actor_user_id=admin.user_id,
            full_name="Yo Mismo",
        )
        assert result.full_name == "Yo Mismo"

    def test_ejec_si_puede_autodesactivarse(self, service, repo, make_user):
        """La restricción es solo para ADMIN."""
        ejec = repo.seed(make_user(role="EJEC"))
        result = service.update(
            user_id=ejec.user_id,
            actor_user_id=ejec.user_id,
            is_active=False,
        )
        assert result.is_active is False
