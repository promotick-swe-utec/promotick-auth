import os
from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import UserNotFoundError
from src.domain.services import UpdateUserService
from src.domain.user import InvalidRoleError
from src.shared.audit import audit_log, user_target
from src.shared.http import claims, json_response, parse_body, require_admin

_service = UpdateUserService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)


def handler(event, context):
    path = event.get("pathParameters") or {}
    user_id = path.get("user_id") or ""
    target = user_target(user_id)
    try:
        require_admin(event)
        if not user_id:
            audit_log(event, "user.updated", "failed", target, 400, error="user_id es requerido")
            return json_response(400, {"error": "user_id es requerido"})

        body = parse_body(event)
        actor = claims(event).get("custom:user_id") or claims(event).get("sub", "")

        is_active_raw = body.get("is_active")
        if is_active_raw is not None and not isinstance(is_active_raw, bool):
            audit_log(
                event,
                "user.updated",
                "failed",
                target,
                400,
                error="is_active debe ser un boolean (true/false), no un string",
            )
            return json_response(
                400,
                {"error": "is_active debe ser un boolean (true/false), no un string"},
            )

        changes = {
            "full_name": body.get("full_name"),
            "role": body.get("role"),
            "is_active": is_active_raw,
        }
        user = _service.update(
            user_id=user_id,
            actor_user_id=actor,
            full_name=body.get("full_name"),
            role=body.get("role"),
            is_active=is_active_raw,
        )
        audit_log(
            event,
            event_type="user.updated",
            status="success",
            target_key=target,
            status_code=200,
            metadata={k: v for k, v in changes.items() if v is not None},
        )
        return json_response(200, {"user": user})
    except (InvalidRoleError, ValueError) as e:
        audit_log(event, "user.updated", "failed", target, 400, error=str(e))
        return json_response(400, {"error": str(e)})
    except PermissionError as e:
        audit_log(event, "user.updated", "denied", target, 403, error=str(e))
        return json_response(403, {"error": str(e)})
    except UserNotFoundError as e:
        audit_log(event, "user.updated", "failed", target, 404, error=str(e))
        return json_response(404, {"error": str(e)})
