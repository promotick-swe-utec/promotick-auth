import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.domain.ports import (
    InvalidConfirmationCodeError,
    InvalidCredentialsError,
    InvalidPasswordError,
    UserNotFoundError,
)
from src.domain.services import ForgotPasswordService
from src.handlers._http import json_response, parse_body


_service = ForgotPasswordService(
    auth=CognitoAuthAdapter(
        user_pool_id=os.environ["USER_POOL_ID"],
        client_id=os.environ["USER_POOL_CLIENT_ID"],
    ),
)


def handler(event, context):
    try:
        body = parse_body(event)
        email = (body.get("email") or "").strip()
        code = (body.get("code") or "").strip()
        new_password = body.get("new_password") or ""
        _service.confirm(email=email, code=code, new_password=new_password)
        return json_response(
            200,
            {"message": "Contraseña actualizada correctamente, ya puedes iniciar sesión"},
        )
    except ValueError as e:
        return json_response(400, {"error": str(e)})
    except InvalidConfirmationCodeError as e:
        return json_response(400, {"error": str(e)})
    except InvalidPasswordError as e:
        return json_response(400, {"error": str(e)})
    except InvalidCredentialsError as e:
        return json_response(401, {"error": str(e)})
    except UserNotFoundError as e:
        return json_response(404, {"error": str(e)})
