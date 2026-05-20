
import socket

from src.domain.ports import EmailValidator
from src.domain.user import InvalidEmailError, _EMAIL_RE

_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "tempmail.com",
        "tempmail.net",
        "10minutemail.com",
        "guerrillamail.com",
        "trashmail.com",
        "throwaway.email",
        "yopmail.com",
        "fakemail.net",
        "sharklasers.com",
        "dispostable.com",
        "getnada.com",
    }
)

_DOMAIN_TYPOS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.co": "gmail.com",
    "gnail.com": "gmail.com",
    "hotnail.com": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "hotmai.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "yhaoo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "outloook.com": "outlook.com",
    "outlok.com": "outlook.com",
    "outlook.con": "outlook.com",
}


class StrictEmailValidator(EmailValidator):

    def __init__(self, check_dns: bool = True, dns_timeout: float = 2.0):
        self._check_dns = check_dns
        self._dns_timeout = dns_timeout

    def validate(self, email: str) -> None:
        if not email:
            raise InvalidEmailError("El correo es obligatorio")

        normalized = email.strip().lower()
        if len(normalized) > 254:
            raise InvalidEmailError("El correo es demasiado largo (máx 254 caracteres)")

        if not _EMAIL_RE.match(normalized):
            raise InvalidEmailError(f"El formato del correo no es válido: {email!r}")

        local, domain = normalized.rsplit("@", 1)

        if len(local) > 64:
            raise InvalidEmailError(
                "La parte local del correo (antes del @) no puede exceder 64 caracteres"
            )

        if domain in _DISPOSABLE_DOMAINS:
            raise InvalidEmailError(
                f"No se permiten correos de dominios desechables ({domain})"
            )

        if domain in _DOMAIN_TYPOS:
            sugerido = _DOMAIN_TYPOS[domain]
            raise InvalidEmailError(
                f"El dominio '{domain}' parece tener un error tipográfico. "
                f"¿Quisiste decir '{sugerido}'?"
            )

        if self._check_dns and not self._domain_resolves(domain):
            raise InvalidEmailError(
                f"El dominio '{domain}' no existe o no resuelve en DNS"
            )

    def _domain_resolves(self, domain: str) -> bool:
        prev = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._dns_timeout)
        try:
            socket.gethostbyname(domain)
            return True
        except socket.gaierror:
            return False
        except OSError:
            return True
        finally:
            socket.setdefaulttimeout(prev)
