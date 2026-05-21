from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.ports import (  # noqa: E402
    AuthTokens,
    UserNotFoundError,
)
from src.domain.user import User  # noqa: E402

class FakeUserRepository:
    

    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}

    # API del puerto
    def save_if_absent(self, user: User) -> bool:
        if user.user_id in self._by_id:
            return False
        self._by_id[user.user_id] = user
        return True

    def exists_by_email(self, email: str) -> bool:
        return self.find_by_email(email) is not None

    def find_by_email(self, email: str) -> Optional[User]:
        target = (email or "").strip().lower()
        for u in self._by_id.values():
            if u.email == target:
                return u
        return None

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._by_id.get(user_id)

    def list_all(self, limit: int = 100) -> Sequence[User]:
        return list(self._by_id.values())[:limit]

    def update(self, user: User) -> User:
        if user.user_id not in self._by_id:
            raise UserNotFoundError(f"Usuario {user.user_id} no existe")
        self._by_id[user.user_id] = user
        return user

    # Helpers de test
    def seed(self, user: User) -> User:
        self._by_id[user.user_id] = user
        return user


class FakeAuthProvider:

    def __init__(self, tokens: Optional[AuthTokens] = None) -> None:
        self.tokens = tokens or AuthTokens(
            id_token="id-tok",
            access_token="acc-tok",
            refresh_token="ref-tok",
            expires_in=3600,
            token_type="Bearer",
        )
        # Excepciones a lanzar
        self.authenticate_error: Optional[Exception] = None
        self.admin_create_error: Optional[Exception] = None
        self.respond_challenge_error: Optional[Exception] = None
        self.start_forgot_error: Optional[Exception] = None
        self.confirm_forgot_error: Optional[Exception] = None

        self.next_sub: str = "cognito-sub-1"

        self.calls: list[tuple[str, dict]] = []

    def authenticate(self, email: str, password: str) -> AuthTokens:
        self.calls.append(("authenticate", {"email": email, "password": password}))
        if self.authenticate_error:
            raise self.authenticate_error
        return self.tokens

    def admin_create_user(self, email: str, full_name: str, role: str) -> str:
        self.calls.append(
            ("admin_create_user", {"email": email, "full_name": full_name, "role": role})
        )
        if self.admin_create_error:
            raise self.admin_create_error
        return self.next_sub

    def set_user_enabled(self, email: str, enabled: bool) -> None:
        self.calls.append(("set_user_enabled", {"email": email, "enabled": enabled}))

    def set_user_role(self, email: str, old_role: str, new_role: str) -> None:
        self.calls.append(
            ("set_user_role", {"email": email, "old_role": old_role, "new_role": new_role})
        )

    def respond_new_password_challenge(
        self, email: str, new_password: str, session: str
    ) -> AuthTokens:
        self.calls.append(
            (
                "respond_new_password_challenge",
                {"email": email, "new_password": new_password, "session": session},
            )
        )
        if self.respond_challenge_error:
            raise self.respond_challenge_error
        return self.tokens

    def start_forgot_password(self, email: str) -> None:
        self.calls.append(("start_forgot_password", {"email": email}))
        if self.start_forgot_error:
            raise self.start_forgot_error

    def confirm_forgot_password(
        self, email: str, code: str, new_password: str
    ) -> None:
        self.calls.append(
            (
                "confirm_forgot_password",
                {"email": email, "code": code, "new_password": new_password},
            )
        )
        if self.confirm_forgot_error:
            raise self.confirm_forgot_error


class FakeRateLimiter:
    """Por defecto deja pasar todo. Configurable para lanzar TooManyAttempts."""

    def __init__(self) -> None:
        self.error: Optional[Exception] = None
        self.calls: list[str] = []

    def check(self, email: str) -> None:
        self.calls.append(email)
        if self.error:
            raise self.error


class FakeEmailValidator:
    """Por defecto valida cualquier email. Configurable para rechazar."""

    def __init__(self) -> None:
        self.error: Optional[Exception] = None
        self.calls: list[str] = []

    def validate(self, email: str) -> None:
        self.calls.append(email)
        if self.error:
            raise self.error


@pytest.fixture
def repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def auth() -> FakeAuthProvider:
    return FakeAuthProvider()


@pytest.fixture
def rate_limiter() -> FakeRateLimiter:
    return FakeRateLimiter()


@pytest.fixture
def email_validator() -> FakeEmailValidator:
    return FakeEmailValidator()


@pytest.fixture
def make_user():

    def _make(
        email: str = "alice@example.com",
        full_name: str = "Alice",
        role: str = "EJEC",
        cognito_sub: str = "sub-alice",
    ) -> User:
        return User.new(
            cognito_sub=cognito_sub,
            email=email,
            full_name=full_name,
            role=role,
        )

    return _make
