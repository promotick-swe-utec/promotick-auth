from dataclasses import dataclass
from typing import Optional, Sequence

from .ports import (
    AuthProvider,
    AuthTokens,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
    UserRepository,
)
from .user import User, _validate_role


@dataclass(frozen=True)
class LoginResult:
    tokens: AuthTokens
    user: User


class LoginService:
    def __init__(self, repo: UserRepository, auth: AuthProvider):
        self._repo = repo
        self._auth = auth

    def login(self, email: str, password: str) -> LoginResult:
        if not email or not password:
            raise InvalidCredentialsError("Email y password son obligatorios")

        tokens = self._auth.authenticate(email=email, password=password)
        user = self._repo.find_by_email(email.strip().lower())
        if user is None:
            raise UserNotFoundError(
                "El usuario autenticó en Cognito pero no tiene perfil en el sistema"
            )
        if not user.is_active:
            raise UserDisabledError("Usuario inactivo")
        return LoginResult(tokens=tokens, user=user)


class CompleteNewPasswordService:
    def __init__(self, repo: UserRepository, auth: AuthProvider):
        self._repo = repo
        self._auth = auth

    def complete(
        self, email: str, new_password: str, session: str
    ) -> LoginResult:
        if not email or not new_password or not session:
            raise InvalidCredentialsError(
                "Email, nueva contraseña y session son obligatorios"
            )

        tokens = self._auth.respond_new_password_challenge(
            email=email, new_password=new_password, session=session
        )
        user = self._repo.find_by_email(email.strip().lower())
        if user is None:
            raise UserNotFoundError(
                "El usuario completó el challenge pero no tiene perfil en el sistema"
            )
        if not user.is_active:
            raise UserDisabledError("Usuario inactivo")
        return LoginResult(tokens=tokens, user=user)


class CreateUserService:

    def __init__(self, repo: UserRepository, auth: AuthProvider):
        self._repo = repo
        self._auth = auth

    def create(self, email: str, full_name: str, role: str) -> User:
        _validate_role(role)
        if self._repo.exists_by_email(email):
            raise UserAlreadyExistsError(
                "El correo electrónico ya se encuentra asociado a una cuenta existente"
            )
        cognito_sub = self._auth.admin_create_user(
            email=email, full_name=full_name, role=role
        )
        user = User.new(
            cognito_sub=cognito_sub,
            email=email,
            full_name=full_name,
            role=role,
        )
        created = self._repo.save_if_absent(user)
        if not created:
            raise UserAlreadyExistsError("Conflicto al persistir el usuario")
        return user


class ListUsersService:
    def __init__(self, repo: UserRepository):
        self._repo = repo

    def list(self, limit: int = 100) -> Sequence[User]:
        return self._repo.list_all(limit=limit)


class UpdateUserService:
    def __init__(self, repo: UserRepository, auth: AuthProvider):
        self._repo = repo
        self._auth = auth

    def update(
        self,
        user_id: str,
        actor_user_id: str,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        current = self._repo.get_by_id(user_id)
        if current is None:
            raise UserNotFoundError(f"Usuario {user_id} no existe")

        # un Admin no puede desactivarse a sí mismo.
        if (
            is_active is False
            and actor_user_id == user_id
            and current.role == "ADMIN"
        ):
            raise PermissionError(
                "Un Administrador no puede desactivar su propia cuenta"
            )

        updated = current.with_changes(
            full_name=full_name, role=role, is_active=is_active
        )
        saved = self._repo.update(updated)

        if is_active is not None and is_active != current.is_active:
            self._auth.set_user_enabled(email=current.email, enabled=bool(is_active))

        return saved
