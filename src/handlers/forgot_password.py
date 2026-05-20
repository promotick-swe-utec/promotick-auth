import os

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.domain.ports import InvalidCredentialsError
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
        _service.start(email=email)
        return json_response(
            200,
            {
                "message": (
                    "Si el correo está registrado, recibirás un código de "
                    "verificación de 6 dígitos en los próximos minutos."
                )
            },
        )
    except ValueError as e:
        return json_response(400, {"error": str(e)})
    except InvalidCredentialsError as e:
        return json_response(400, {"error": str(e)})
