from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from .user import User


@dataclass(frozen=True)
class AuthTokens:
    id_token: str
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str


class UserNotFoundError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserDisabledError(Exception):
    pass


class UserRepository(Protocol):
    def save_if_absent(self, user: User) -> bool:
        ...

    def exists_by_email(self, email: str) -> bool:
        ...

    def find_by_email(self, email: str) -> Optional[User]:
        ...

    def get_by_id(self, user_id: str) -> Optional[User]:
        ...

    def list_all(self, limit: int = 100) -> Sequence[User]:
        ...

    def update(self, user: User) -> User:
        ...


class AuthProvider(Protocol):
    def authenticate(self, email: str, password: str) -> AuthTokens:
        ... # Devuelve los tokens emitidos por el IdP.

    def admin_create_user(self, email: str, full_name: str, role: str) -> str:
        ... # Crea el usuario en el IdP y devuelve su sub (identificador único de cognito).

    def set_user_enabled(self, email: str, enabled: bool) -> None:
        ... #Habilita/inhabilita el usuario en el IdP
