import boto3
from botocore.exceptions import ClientError

from src.domain.ports import (
    AuthProvider,
    AuthTokens,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
)


class CognitoAuthAdapter(AuthProvider):
    """Implementación de AuthProvider sobre AWS Cognito User Pool."""

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        client=None,
    ):
        self._pool_id = user_pool_id
        self._client_id = client_id
        self._cognito = client or boto3.client("cognito-idp")

    # ---------- AuthProvider ----------

    def authenticate(self, email: str, password: str) -> AuthTokens:
        try:
            resp = self._cognito.admin_initiate_auth(
                UserPoolId=self._pool_id,
                ClientId=self._client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password,
                },
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("NotAuthorizedException", "UserNotFoundException"):
                raise InvalidCredentialsError("Credenciales inválidas") from e
            if code == "UserNotConfirmedException":
                raise InvalidCredentialsError(
                    "Usuario aún no confirmó su contraseña inicial"
                ) from e
            if code == "PasswordResetRequiredException":
                raise InvalidCredentialsError(
                    "Se requiere reseteo de contraseña"
                ) from e
            raise

        auth = resp.get("AuthenticationResult")
        if not auth:
            # Cognito devolvió un Challenge (NEW_PASSWORD_REQUIRED, MFA, ...).
            raise InvalidCredentialsError(
                f"Login requiere paso adicional: {resp.get('ChallengeName')}"
            )
        return AuthTokens(
            id_token=auth["IdToken"],
            access_token=auth["AccessToken"],
            refresh_token=auth.get("RefreshToken", ""),
            expires_in=int(auth["ExpiresIn"]),
            token_type=auth["TokenType"],
        )

    def admin_create_user(self, email: str, full_name: str, role: str) -> str:
        normalized = email.strip().lower()
        try:
            resp = self._cognito.admin_create_user(
                UserPoolId=self._pool_id,
                Username=normalized,
                UserAttributes=[
                    {"Name": "email", "Value": normalized},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": full_name or normalized.split("@")[0]},
                ],
                DesiredDeliveryMediums=["EMAIL"],
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "UsernameExistsException":
                raise UserAlreadyExistsError(
                    "El correo electrónico ya se encuentra asociado a una cuenta existente"
                ) from e
            raise

        attrs = {a["Name"]: a["Value"] for a in resp["User"]["Attributes"]}
        sub = attrs.get("sub")
        if not sub:
            raise RuntimeError("Cognito no devolvió 'sub' al crear el usuario")

        try:
            self._cognito.admin_add_user_to_group(
                UserPoolId=self._pool_id,
                Username=normalized,
                GroupName=role,
            )
        except ClientError as e:
            self._cognito.admin_delete_user(
                UserPoolId=self._pool_id, Username=normalized
            )
            code = e.response["Error"]["Code"]
            if code == "ResourceNotFoundException":
                raise RuntimeError(
                    f"El grupo Cognito '{role}' no existe. Despliega promotick-infra-cognito."
                ) from e
            raise

        return sub

    def set_user_enabled(self, email: str, enabled: bool) -> None:
        normalized = email.strip().lower()
        try:
            if enabled:
                self._cognito.admin_enable_user(
                    UserPoolId=self._pool_id, Username=normalized
                )
            else:
                self._cognito.admin_disable_user(
                    UserPoolId=self._pool_id, Username=normalized
                )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "UserNotFoundException":
                raise UserNotFoundError(
                    f"Usuario {normalized} no existe en Cognito"
                ) from e
            if code == "NotAuthorizedException":
                raise UserDisabledError("No autorizado") from e
            raise
