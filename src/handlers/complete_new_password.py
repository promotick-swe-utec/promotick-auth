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
from src.shared.audit import audit_log, email_target, user_target
from src.shared.http import json_response, parse_body


_EVENT_TYPE = "auth.complete_new_password"

_service = CompleteNewPasswordService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)


def handler(event, context):
    email = ""
    try:
        body = parse_body(event)
        email = (body.get("email") or "").strip()
        new_password = body.get("new_password") or ""
        session = body.get("session") or ""
        result = _service.complete(
            email=email, new_password=new_password, session=session
        )
        audit_log(
            event,
            event_type=_EVENT_TYPE,
            status="success",
            target_key=user_target(result.user.user_id),
            status_code=200,
            metadata={"email": email},
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
    except (ValueError, InvalidPasswordError) as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 400, error=str(e))
        return json_response(400, {"error": str(e)})
    except InvalidCredentialsError as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 401, error=str(e))
        return json_response(401, {"error": str(e)})
    except UserDisabledError as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 403, error=str(e))
        return json_response(403, {"error": str(e)})
    except UserNotFoundError as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 404, error=str(e))
        return json_response(404, {"error": str(e)})
