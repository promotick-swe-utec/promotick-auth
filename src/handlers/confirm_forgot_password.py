import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.domain.ports import (
    InvalidConfirmationCodeError,
    InvalidCredentialsError,
    InvalidPasswordError,
    UserNotFoundError,
)
from src.domain.services import ForgotPasswordService
from src.shared.audit import audit_log, email_target
from src.shared.http import json_response, parse_body


_EVENT_TYPE = "auth.forgot_password.confirm"

_service = ForgotPasswordService(
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
        code = (body.get("code") or "").strip()
        new_password = body.get("new_password") or ""
        _service.confirm(email=email, code=code, new_password=new_password)
        audit_log(
            event,
            event_type=_EVENT_TYPE,
            status="success",
            target_key=email_target(email),
            status_code=200,
        )
        return json_response(
            200,
            {"message": "Contraseña actualizada correctamente, ya puedes iniciar sesión"},
        )
    except (ValueError, InvalidConfirmationCodeError, InvalidPasswordError) as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 400, error=str(e))
        return json_response(400, {"error": str(e)})
    except InvalidCredentialsError as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 401, error=str(e))
        return json_response(401, {"error": str(e)})
    except UserNotFoundError as e:
        audit_log(event, _EVENT_TYPE, "failed", email_target(email), 404, error=str(e))
        return json_response(404, {"error": str(e)})
