"""Helpers comunes para handlers detrás de API Gateway (HTTP API v2)."""
import json
from dataclasses import asdict, is_dataclass
from typing import Any


def _default(o: Any):
    if is_dataclass(o):
        return asdict(o)
    raise TypeError(f"Tipo no serializable: {type(o).__name__}")


def json_response(status: int, body: Any) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_default, ensure_ascii=False),
    }


def parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        raise ValueError(f"Body JSON inválido: {e}") from e


def claims(event: dict) -> dict:
    """Claims del JWT inyectados por el authorizer de API Gateway."""
    auth = (event.get("requestContext") or {}).get("authorizer") or {}
    # HTTP API v2: jwt.claims ; REST API: claims directos
    return (auth.get("jwt") or {}).get("claims") or auth.get("claims") or {}


def require_admin(event: dict) -> None:
    c = claims(event)
    groups = c.get("cognito:groups") or c.get("custom:role") or ""
    if isinstance(groups, list):
        roles = set(groups)
    else:
        roles = set(str(groups).replace("[", "").replace("]", "").split(","))
        roles = {r.strip() for r in roles if r.strip()}
    if "ADMIN" not in roles:
        raise PermissionError("Operación restringida al rol ADMIN")
