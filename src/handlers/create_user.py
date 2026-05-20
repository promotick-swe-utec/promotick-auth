import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import UserAlreadyExistsError
from src.domain.services import CreateUserService
from src.domain.user import InvalidEmailError, InvalidRoleError
from src.shared.audit import audit_log, email_target, user_target
from src.shared.http import json_response, parse_body, require_admin

_service = CreateUserService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)

def handler(event, context):
    email = ""
    role = None
    try:
        require_admin(event)
        body = parse_body(event)
        email = (body.get("email") or "").strip()
        role = body.get("role")
        user = _service.create(
            email=body["email"],
            full_name=body.get("full_name", ""),
            role=body["role"],
        )
        audit_log(
            event,
            event_type="user.created",
            status="success",
            target_key=user_target(user.user_id),
            status_code=201,
            metadata={"email": user.email, "role": user.role},
        )
        return json_response(201, {"user": user})
    except KeyError as e:
        msg = f"Campo requerido faltante: {e.args[0]}"
        audit_log(event, "user.created", "failed", email_target(email), 400, error=msg)
        return json_response(400, {"error": msg})
    except (InvalidEmailError, InvalidRoleError, ValueError) as e:
        audit_log(event, "user.created", "failed", email_target(email), 400, error=str(e), metadata={"role": role})
        return json_response(400, {"error": str(e)})
    except PermissionError as e:
        audit_log(event, "user.created", "denied", email_target(email), 403, error=str(e))
        return json_response(403, {"error": str(e)})
    except UserAlreadyExistsError as e:
        audit_log(event, "user.created", "failed", email_target(email), 409, error=str(e))
        return json_response(409, {"error": str(e)})
