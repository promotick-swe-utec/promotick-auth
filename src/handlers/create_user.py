import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import UserAlreadyExistsError
from src.domain.services import CreateUserService
from src.domain.user import InvalidEmailError, InvalidRoleError
from src.handlers._http import json_response, parse_body, require_admin

_service = CreateUserService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)

def handler(event, context):
    try:
        require_admin(event)
        body = parse_body(event)
        user = _service.create(
            email=body["email"],
            full_name=body.get("full_name", ""),
            role=body["role"],
        )
        return json_response(201, {"user": user})
    except KeyError as e:
        return json_response(400, {"error": f"Campo requerido faltante: {e.args[0]}"})
    except (InvalidEmailError, InvalidRoleError, ValueError) as e:
        return json_response(400, {"error": str(e)})
    except PermissionError as e:
        return json_response(403, {"error": str(e)})
    except UserAlreadyExistsError as e:
        return json_response(409, {"error": str(e)})
