import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import (
    InvalidCredentialsError,
    InvalidPasswordError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import CompleteNewPasswordService
from src.handlers._http import json_response, parse_body


_service = CompleteNewPasswordService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)


def handler(event, context):
    try:
        body = parse_body(event)
        email = (body.get("email") or "").strip()
        new_password = body.get("new_password") or ""
        session = body.get("session") or ""
        result = _service.complete(
            email=email, new_password=new_password, session=session
        )
        return json_response(
            200,
            {
                "tokens": {
                    "id_token": result.tokens.id_token,
                    "access_token": result.tokens.access_token,
                    "refresh_token": result.tokens.refresh_token,
                    "expires_in": result.tokens.expires_in,
                    "token_type": result.tokens.token_type,
                },
                "user": result.user,
            },
        )
    except ValueError as e:
        return json_response(400, {"error": str(e)})
    except InvalidPasswordError as e:
        return json_response(400, {"error": str(e)})
    except InvalidCredentialsError as e:
        return json_response(401, {"error": str(e)})
    except UserDisabledError as e:
        return json_response(403, {"error": str(e)})
    except UserNotFoundError as e:
        return json_response(404, {"error": str(e)})
