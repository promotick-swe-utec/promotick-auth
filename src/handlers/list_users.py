import os

from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.services import ListUsersService
from src.handlers._http import json_response, require_admin

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
        return json_response(200, {"users": list(users), "count": len(users)})
    except PermissionError as e:
        return json_response(403, {"error": str(e)})
