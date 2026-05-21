from __future__ import annotations
import uuid
import pytest
from src.domain.user import (
    InvalidEmailError,
    InvalidRoleError,
    User,
    VALID_ROLES,
    _normalize_email,
    _validate_role,
)

pytestmark = pytest.mark.unit

class TestValidateRole:
    @pytest.mark.parametrize("role", ["ADMIN", "EJEC", "VIEWER"])
    def test_acepta_roles_validos(self, role):
        assert _validate_role(role) == role

    @pytest.mark.parametrize("role", ["admin", "superuser", "", "SUPERVISOR", "EJEC "])
    def test_rechaza_roles_invalidos(self, role):
        with pytest.raises(InvalidRoleError):
            _validate_role(role)

    def test_los_roles_validos_son_inmutables(self):
        assert VALID_ROLES == frozenset({"ADMIN", "EJEC", "VIEWER"})


class TestNormalizeEmail:
    def test_normaliza_a_minusculas_y_recorta(self):
        assert _normalize_email("  Alice@Example.COM  ") == "alice@example.com"

    @pytest.mark.parametrize(
        "email",
        [
            "",
            "no-arroba",
            "a@b",                       
            "a..b@example.com",          
            "@example.com",
            "user@",
            "user@.com",
            "user@example..com",
        ],
    )
    def test_rechaza_emails_invalidos(self, email):
        with pytest.raises(InvalidEmailError):
            _normalize_email(email)

    def test_rechaza_email_demasiado_largo(self):
        long_local = "a" * 250
        with pytest.raises(InvalidEmailError, match="demasiado largo"):
            _normalize_email(f"{long_local}@example.com")


class TestUserNew:
    def test_genera_id_uuid_v4_valido(self, make_user):
        user = make_user()
        assert uuid.UUID(user.user_id).version == 4

    def test_normaliza_email(self):
        user = User.new(
            cognito_sub="s",
            email="  Foo@Bar.COM ",
            full_name="x",
            role="EJEC",
        )
        assert user.email == "foo@bar.com"

    def test_full_name_vacio_usa_local_part_del_email(self):
        user = User.new(
            cognito_sub="s",
            email="bob@example.com",
            full_name="   ",
            role="VIEWER",
        )
        assert user.full_name == "bob"

    def test_recorta_full_name(self):
        user = User.new(
            cognito_sub="s",
            email="bob@example.com",
            full_name="  Bob Smith  ",
            role="VIEWER",
        )
        assert user.full_name == "Bob Smith"

    def test_es_activo_por_defecto(self, make_user):
        assert make_user().is_active is True

    def test_created_at_y_updated_at_coinciden_al_crear(self, make_user):
        u = make_user()
        assert u.created_at == u.updated_at

    def test_rechaza_rol_invalido(self):
        with pytest.raises(InvalidRoleError):
            User.new(
                cognito_sub="s",
                email="x@example.com",
                full_name="X",
                role="SUPERVISOR",
            )

    def test_es_inmutable(self, make_user):
        u = make_user()
        with pytest.raises(Exception):
            u.email = "otro@example.com"


class TestWithChanges:
    def test_sin_cambios_solo_actualiza_updated_at(self, make_user):
        u = make_user()
        v = u.with_changes()
        assert v.email == u.email
        assert v.role == u.role
        assert v.is_active == u.is_active
        assert v.full_name == u.full_name
        assert v.updated_at >= u.updated_at

    def test_cambia_role_valido(self, make_user):
        u = make_user(role="EJEC")
        v = u.with_changes(role="ADMIN")
        assert v.role == "ADMIN"
        assert u.role == "EJEC"

    def test_rechaza_role_invalido(self, make_user):
        with pytest.raises(InvalidRoleError):
            make_user().with_changes(role="HACKER")

    def test_cambia_is_active(self, make_user):
        u = make_user()
        assert u.with_changes(is_active=False).is_active is False

    def test_full_name_vacio_no_pisa_el_actual(self, make_user):
        u = make_user(full_name="Original")
        v = u.with_changes(full_name="   ")
        assert v.full_name == "Original"

    def test_full_name_se_recorta(self, make_user):
        u = make_user(full_name="A")
        v = u.with_changes(full_name="  Nuevo Nombre  ")
        assert v.full_name == "Nuevo Nombre"

    def test_preserva_user_id_y_created_at(self, make_user):
        u = make_user()
        v = u.with_changes(full_name="Otro")
        assert v.user_id == u.user_id
        assert v.created_at == u.created_at
