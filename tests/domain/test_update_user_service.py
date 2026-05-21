"""Tests del UpdateUserService.

Reglas de negocio cubiertas:
- Solo se puede desactivar a usuarios con rol EJEC o VIEWER.
- Los ADMIN son intocables: no pueden auto-desactivarse ni ser desactivados
  por otro ADMIN.
- Cambios de role / is_active se sincronizan con Cognito solo si hubo cambio.

Nota arquitectónica: la regla "solo ADMIN puede invocar PATCH /users/{id}"
vive en el handler (`require_admin`), no aquí. El servicio asume que ya pasó
ese filtro y se enfoca en las reglas sobre el usuario *objetivo*.
"""
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


class TestDesactivacionDePermitidos:
    """EJEC y VIEWER sí pueden ser desactivados por un ADMIN."""

    @pytest.mark.parametrize("target_role", ["EJEC", "VIEWER"])
    def test_admin_desactiva_a_ejec_o_viewer(
        self, service, repo, auth, make_user, target_role
    ):
        target = repo.seed(
            make_user(role=target_role, email="t@example.com", cognito_sub="s-t")
        )
        result = service.update(
            user_id=target.user_id, actor_user_id="admin-id", is_active=False
        )
        assert result.is_active is False
        assert (
            "set_user_enabled",
            {"email": "t@example.com", "enabled": False},
        ) in auth.calls

    def test_no_toca_cognito_si_is_active_no_cambia(
        self, service, repo, auth, make_user
    ):
        u = repo.seed(make_user(role="EJEC"))
        service.update(user_id=u.user_id, actor_user_id="admin", is_active=True)
        assert not any(c[0] == "set_user_enabled" for c in auth.calls)


class TestAdminEsIntocable:
    """Ningún ADMIN puede ser desactivado — ni por sí mismo ni por otro ADMIN."""

    def test_admin_no_puede_autodesactivarse(self, service, repo, auth, make_user):
        admin = repo.seed(make_user(role="ADMIN", email="admin@example.com"))

        with pytest.raises(PermissionError, match="su propia cuenta"):
            service.update(
                user_id=admin.user_id,
                actor_user_id=admin.user_id,
                is_active=False,
            )

        # No se persistió ni se sincronizó con Cognito.
        assert repo.get_by_id(admin.user_id).is_active is True
        assert not any(c[0] == "set_user_enabled" for c in auth.calls)

    def test_admin_no_puede_desactivar_a_otro_admin(
        self, service, repo, auth, make_user
    ):
        otro = repo.seed(
            make_user(role="ADMIN", email="otro@example.com", cognito_sub="s2")
        )

        with pytest.raises(PermissionError, match="otro Administrador"):
            service.update(
                user_id=otro.user_id,
                actor_user_id="distinto-admin-id",
                is_active=False,
            )

        assert repo.get_by_id(otro.user_id).is_active is True
        assert not any(c[0] == "set_user_enabled" for c in auth.calls)

    def test_admin_puede_editar_nombre_de_otro_admin(
        self, service, repo, make_user
    ):
        """La restricción cubre `is_active` y `role`, no otros campos."""
        otro = repo.seed(
            make_user(role="ADMIN", email="otro@example.com", cognito_sub="s3")
        )
        result = service.update(
            user_id=otro.user_id,
            actor_user_id="admin-id",
            full_name="Nombre Editado",
        )
        assert result.full_name == "Nombre Editado"

    def test_admin_puede_autoactualizar_su_nombre(self, service, repo, make_user):
        admin = repo.seed(make_user(role="ADMIN"))
        result = service.update(
            user_id=admin.user_id,
            actor_user_id=admin.user_id,
            full_name="Yo Mismo",
        )
        assert result.full_name == "Yo Mismo"

    def test_admin_no_puede_cambiar_rol_de_otro_admin(
        self, service, repo, auth, make_user
    ):
        otro = repo.seed(
            make_user(role="ADMIN", email="otro@example.com", cognito_sub="s3")
        )
        with pytest.raises(PermissionError, match="cambiar el rol"):
            service.update(
                user_id=otro.user_id,
                actor_user_id="admin-id",
                role="VIEWER",
            )

        # No se persistió ni se sincronizó con Cognito.
        assert repo.get_by_id(otro.user_id).role == "ADMIN"
        assert not any(c[0] == "set_user_role" for c in auth.calls)

    def test_admin_puede_autocambiar_su_rol(
        self, service, repo, auth, make_user
    ):
        """PLACEHOLDER: comportamiento actual permite auto-democión.

        Si la regla debe ser 'NINGÚN rol de ADMIN se puede cambiar, ni siquiera
        el propio', actualiza este test a `pytest.raises(PermissionError)` y la
        condición en `UpdateUserService.update` removiendo `actor_user_id != user_id`.
        """
        admin = repo.seed(make_user(role="ADMIN", email="me@example.com"))
        result = service.update(
            user_id=admin.user_id,
            actor_user_id=admin.user_id,
            role="VIEWER",
        )
        assert result.role == "VIEWER"
