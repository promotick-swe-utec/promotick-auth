import boto3
from botocore.exceptions import ClientError

from src.domain.ports import (
    AuthProvider,
    AuthTokens,
    InvalidConfirmationCodeError,
    InvalidCredentialsError,
    InvalidPasswordError,
    NewPasswordRequiredError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
)


class CognitoAuthAdapter(AuthProvider):

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        client=None,
    ):
        self._pool_id = user_pool_id
        self._client_id = client_id
        self._cognito = client or boto3.client("cognito-idp")

    # AuthProvider 

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
            message = e.response["Error"].get("Message", "")
            if code == "NotAuthorizedException" and "disabled" in message.lower():
                raise UserDisabledError("Usuario inactivo") from e
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
            challenge = resp.get("ChallengeName")
            if challenge == "NEW_PASSWORD_REQUIRED":
                raise NewPasswordRequiredError(
                    session=resp.get("Session", ""),
                    email=email.strip().lower(),
                )
            raise InvalidCredentialsError(
                f"Login requiere paso adicional: {challenge}"
            )
        return self._tokens_from_auth_result(auth)

    def respond_new_password_challenge(self, email: str, new_password: str, session: str) -> AuthTokens:
        normalized = email.strip().lower()
        try:
            resp = self._cognito.admin_respond_to_auth_challenge(
                UserPoolId=self._pool_id,
                ClientId=self._client_id,
                ChallengeName="NEW_PASSWORD_REQUIRED",
                Session=session,
                ChallengeResponses={
                    "USERNAME": normalized,
                    "NEW_PASSWORD": new_password,
                },
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            message = e.response["Error"].get("Message", "")
            if code in ("InvalidPasswordException", "InvalidParameterException"):
                raise InvalidPasswordError(message) from e
            if code in ("NotAuthorizedException", "CodeMismatchException"):
                raise InvalidCredentialsError(
                    "Sesión expirada o inválida, vuelve a iniciar sesión"
                ) from e
            if code == "UserNotFoundException":
                raise UserNotFoundError(
                    f"Usuario {normalized} no existe en Cognito"
                ) from e
            raise

        auth = resp.get("AuthenticationResult")
        if not auth:
            raise InvalidCredentialsError(
                f"No se pudo completar el challenge: {resp.get('ChallengeName')}"
            )
        return self._tokens_from_auth_result(auth)

    @staticmethod
    def _tokens_from_auth_result(auth: dict) -> AuthTokens:
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
                    f"El grupo Cognito '{role}' no existe. Verifica infrastructure/cognito.yml en promotick-auth."
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

    def set_user_role(self, email: str, old_role: str, new_role: str) -> None:
        if old_role == new_role:
            return
        normalized = email.strip().lower()
        try:
            self._cognito.admin_add_user_to_group(
                UserPoolId=self._pool_id,
                Username=normalized,
                GroupName=new_role,
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ResourceNotFoundException":
                raise RuntimeError(
                    f"El grupo Cognito '{new_role}' no existe. Verifica infrastructure/cognito.yml en promotick-auth."
                ) from e
            if code == "UserNotFoundException":
                raise UserNotFoundError(
                    f"Usuario {normalized} no existe en Cognito"
                ) from e
            raise

        try:
            self._cognito.admin_remove_user_from_group(
                UserPoolId=self._pool_id,
                Username=normalized,
                GroupName=old_role,
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ResourceNotFoundException":
                return
            raise

    def start_forgot_password(self, email: str) -> None:
        normalized = email.strip().lower()
        try:
            self._cognito.forgot_password(
                ClientId=self._client_id,
                Username=normalized,
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "UserNotFoundException":
                return
            if code == "LimitExceededException":
                raise InvalidCredentialsError(
                    "Se excedió el límite de intentos, intenta más tarde"
                ) from e
            if code == "NotAuthorizedException":
                raise InvalidCredentialsError(
                    "El usuario no puede resetear su contraseña en su estado actual"
                ) from e
            raise

    def confirm_forgot_password(self, email: str, code: str, new_password: str) -> None:
        normalized = email.strip().lower()
        try:
            self._cognito.confirm_forgot_password(
                ClientId=self._client_id,
                Username=normalized,
                ConfirmationCode=code,
                Password=new_password,
            )
        except ClientError as e:
            err_code = e.response["Error"]["Code"]
            message = e.response["Error"].get("Message", "")
            if err_code in ("CodeMismatchException", "ExpiredCodeException"):
                raise InvalidConfirmationCodeError(
                    "El código es inválido o ya expiró"
                ) from e
            if err_code in ("InvalidPasswordException", "InvalidParameterException"):
                raise InvalidPasswordError(message) from e
            if err_code == "UserNotFoundException":
                raise UserNotFoundError(
                    f"Usuario {normalized} no existe en Cognito"
                ) from e
            if err_code == "LimitExceededException":
                raise InvalidCredentialsError(
                    "Se excedió el límite de intentos, intenta más tarde"
                ) from e
            raise
