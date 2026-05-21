import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional

VALID_ROLES = frozenset({"ADMIN", "EJEC", "VIEWER"})

_EMAIL_RE = re.compile(
    r"^(?!.*\.\.)[A-Za-z0-9._%+\-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,}$"
)


class InvalidRoleError(ValueError):
    pass


class InvalidEmailError(ValueError):
    pass


_DOTLESS_LOCAL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def _normalize_email(email: str) -> str:
    if not email:
        raise InvalidEmailError("Email vacío")
    normalized = email.strip().lower()
    if len(normalized) > 254:
        raise InvalidEmailError("Email demasiado largo (máx 254 caracteres)")
    if not _EMAIL_RE.match(normalized):
        raise InvalidEmailError(f"Formato de email inválido: {email!r}")
    return normalized


def canonicalize_email(email: str) -> str:
    normalized = _normalize_email(email)
    local, domain = normalized.rsplit("@", 1)

    if "+" in local:
        local = local.split("+", 1)[0]

    if domain in _DOTLESS_LOCAL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"

    if not local:
        raise InvalidEmailError(
            "La parte local del correo no puede quedar vacía tras la normalización"
        )

    return f"{local}@{domain}"


def _validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise InvalidRoleError(
            f"Rol inválido: {role!r}. Permitidos: {sorted(VALID_ROLES)}"
        )
    return role


@dataclass(frozen=True)
class User:
    user_id: str
    cognito_sub: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str

    @classmethod
    def new(
        cls,
        cognito_sub: str,
        email: str,
        full_name: str,
        role: str,
    ) -> "User":
        now = datetime.now(timezone.utc).isoformat()
        canonical_email = canonicalize_email(email)
        return cls(
            user_id=str(uuid.uuid4()),
            cognito_sub=cognito_sub,
            email=canonical_email,
            full_name=(full_name or "").strip() or canonical_email.split("@")[0],
            role=_validate_role(role),
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    def with_changes(
        self,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> "User":
        return replace(
            self,
            full_name=self.full_name if full_name is None else full_name.strip() or self.full_name,
            role=self.role if role is None else _validate_role(role),
            is_active=self.is_active if is_active is None else bool(is_active),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
