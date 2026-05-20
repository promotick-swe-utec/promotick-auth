import os
from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.adapters.dynamo_login_rate_limiter import DynamoLoginRateLimiter
from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import (
    InvalidCredentialsError,
    NewPasswordRequiredError,
    TooManyAttemptsError,
    UserDisabledError,
    UserNotFoundError,
)
from src.domain.services import LoginService
from src.shared.audit import audit_log, email_target, user_target
from src.shared.http import json_response, parse_body


_service = LoginService(
    repo=DynamoUserRepository(table_name=os.environ["USERS_TABLE_NAME"]),
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
    rate_limiter=DynamoLoginRateLimiter(
        table_name=os.environ["AUDIT_LOGS_TABLE_NAME"],
    ),
)


def handler(event, context):
    email = ""
    try:
        body = parse_body(event)
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        result = _service.login(email=email, password=password)
        audit_log(
            event,
            event_type="auth.login",
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
    except ValueError as e:
        audit_log(event, "auth.login", "failed", email_target(email), 400, error=str(e))
        return json_response(400, {"error": str(e)})
    except TooManyAttemptsError as e:
        audit_log(
            event,
            "auth.login",
            "blocked",
            email_target(email),
            429,
            metadata={"retry_after": e.retry_after_seconds},
        )
        return json_response(
            429,
            {"error": str(e), "retry_after": e.retry_after_seconds},
            headers={"Retry-After": str(e.retry_after_seconds)},
        )
    except NewPasswordRequiredError as e:
        audit_log(
            event,
            event_type="auth.login",
            status="challenge",
            target_key=email_target(email),
            status_code=200,
            metadata={"challenge": "NEW_PASSWORD_REQUIRED"},
        )
        return json_response(
            200,
            {
                "challenge": "NEW_PASSWORD_REQUIRED",
                "session": e.session,
                "email": e.email,
                "message": str(e),
            },
        )
    except InvalidCredentialsError as e:
        audit_log(event, "auth.login", "failed", email_target(email), 401, error=str(e))
        return json_response(401, {"error": str(e)})
    except UserDisabledError as e:
        audit_log(event, "auth.login", "failed", email_target(email), 403, error=str(e))
        return json_response(403, {"error": str(e)})
    except UserNotFoundError as e:
        audit_log(event, "auth.login", "failed", email_target(email), 404, error=str(e))
        return json_response(404, {"error": str(e)})
