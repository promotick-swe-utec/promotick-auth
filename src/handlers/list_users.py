import os

from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.services import ListUsersService
from src.shared.audit import audit_log
from src.shared.http import json_response, require_admin

_service = ListUsersService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
)


def handler(event, context):
    try:
        require_admin(event)
        qs = event.get("queryStringParameters") or {}
        try:
            limit = max(1, min(int(qs.get("limit", 50)), 1000))
        except (TypeError, ValueError):
            limit = 50
        users = _service.list(limit=limit)
        audit_log(
            event,
            event_type="user.listed",
            status="success",
            target_key="users#list",
            status_code=200,
            metadata={"limit": limit, "count": len(users)},
        )
        return json_response(200, {"users": list(users), "count": len(users)})
    except PermissionError as e:
        audit_log(event, "user.listed", "denied", "users#list", 403, error=str(e))
        return json_response(403, {"error": str(e)})
