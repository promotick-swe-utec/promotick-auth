from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.adapters.cognito_auth_adapter import CognitoAuthAdapter
from src.domain.ports import (
    InvalidConfirmationCodeError,
    InvalidCredentialsError,
    InvalidPasswordError,
    NewPasswordRequiredError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
)

pytestmark = pytest.mark.unit


def _err(code: str, message: str = "") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "Op")


def _auth_result() -> dict:
    return {
        "IdToken": "id",
        "AccessToken": "acc",
        "RefreshToken": "ref",
        "ExpiresIn": 3600,
        "TokenType": "Bearer",
    }


def _adapter(client: MagicMock) -> CognitoAuthAdapter:
    return CognitoAuthAdapter(user_pool_id="pool", client_id="client", client=client)


class TestAuthenticate:
    def test_success_returns_tokens(self):
        client = MagicMock()
        client.admin_initiate_auth.return_value = {"AuthenticationResult": _auth_result()}
        tokens = _adapter(client).authenticate("x@y.z", "p")
        assert tokens.id_token == "id"
        assert tokens.expires_in == 3600

    def test_not_authorized_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_initiate_auth.side_effect = _err("NotAuthorizedException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).authenticate("x@y.z", "p")

    def test_user_not_found_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_initiate_auth.side_effect = _err("UserNotFoundException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).authenticate("x@y.z", "p")

    def test_user_not_confirmed_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_initiate_auth.side_effect = _err("UserNotConfirmedException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).authenticate("x@y.z", "p")

    def test_password_reset_required_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_initiate_auth.side_effect = _err("PasswordResetRequiredException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).authenticate("x@y.z", "p")

    def test_unknown_error_reraises(self):
        client = MagicMock()
        client.admin_initiate_auth.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).authenticate("x@y.z", "p")

    def test_new_password_challenge(self):
        client = MagicMock()
        client.admin_initiate_auth.return_value = {
            "ChallengeName": "NEW_PASSWORD_REQUIRED",
            "Session": "sess-1",
        }
        with pytest.raises(NewPasswordRequiredError) as exc:
            _adapter(client).authenticate("X@Y.Z", "p")
        assert exc.value.session == "sess-1"
        assert exc.value.email == "x@y.z"

    def test_other_challenge_raises_invalid_credentials(self):
        client = MagicMock()
        client.admin_initiate_auth.return_value = {"ChallengeName": "SMS_MFA"}
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).authenticate("x@y.z", "p")


class TestRespondNewPasswordChallenge:
    def test_success_returns_tokens(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.return_value = {
            "AuthenticationResult": _auth_result()
        }
        tokens = _adapter(client).respond_new_password_challenge("x@y.z", "new", "sess")
        assert tokens.access_token == "acc"

    def test_invalid_password_error(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err(
            "InvalidPasswordException", "weak"
        )
        with pytest.raises(InvalidPasswordError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_invalid_parameter_maps_to_invalid_password(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err(
            "InvalidParameterException", "bad"
        )
        with pytest.raises(InvalidPasswordError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_not_authorized_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err("NotAuthorizedException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_code_mismatch_maps_to_invalid_credentials(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err("CodeMismatchException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_user_not_found(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err("UserNotFoundException")
        with pytest.raises(UserNotFoundError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_unknown_error_reraises(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")

    def test_no_authentication_result_raises(self):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.return_value = {"ChallengeName": "MFA"}
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).respond_new_password_challenge("x@y.z", "n", "s")


class TestAdminCreateUser:
    def _resp(self, sub: str = "sub-1") -> dict:
        return {
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": sub},
                    {"Name": "email", "Value": "x@y.z"},
                ]
            }
        }

    def test_success_returns_sub(self):
        client = MagicMock()
        client.admin_create_user.return_value = self._resp()
        sub = _adapter(client).admin_create_user("X@Y.Z", "Name", "EJEC")
        assert sub == "sub-1"
        client.admin_add_user_to_group.assert_called_once()

    def test_uses_local_part_when_no_full_name(self):
        client = MagicMock()
        client.admin_create_user.return_value = self._resp()
        _adapter(client).admin_create_user("alice@y.z", "", "EJEC")
        attrs = client.admin_create_user.call_args.kwargs["UserAttributes"]
        name_attr = next(a for a in attrs if a["Name"] == "name")
        assert name_attr["Value"] == "alice"

    def test_already_exists(self):
        client = MagicMock()
        client.admin_create_user.side_effect = _err("UsernameExistsException")
        with pytest.raises(UserAlreadyExistsError):
            _adapter(client).admin_create_user("x@y.z", "X", "EJEC")

    def test_unknown_create_error_reraises(self):
        client = MagicMock()
        client.admin_create_user.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).admin_create_user("x@y.z", "X", "EJEC")

    def test_missing_sub_raises(self):
        client = MagicMock()
        client.admin_create_user.return_value = {
            "User": {"Attributes": [{"Name": "email", "Value": "x@y.z"}]}
        }
        with pytest.raises(RuntimeError):
            _adapter(client).admin_create_user("x@y.z", "X", "EJEC")

    def test_group_missing_rolls_back_and_raises(self):
        client = MagicMock()
        client.admin_create_user.return_value = self._resp()
        client.admin_add_user_to_group.side_effect = _err("ResourceNotFoundException")
        with pytest.raises(RuntimeError):
            _adapter(client).admin_create_user("x@y.z", "X", "EJEC")
        client.admin_delete_user.assert_called_once()

    def test_group_other_error_rolls_back_and_reraises(self):
        client = MagicMock()
        client.admin_create_user.return_value = self._resp()
        client.admin_add_user_to_group.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).admin_create_user("x@y.z", "X", "EJEC")
        client.admin_delete_user.assert_called_once()


class TestSetUserEnabled:
    def test_enable_calls_admin_enable(self):
        client = MagicMock()
        _adapter(client).set_user_enabled("X@Y.Z", True)
        client.admin_enable_user.assert_called_once()

    def test_disable_calls_admin_disable(self):
        client = MagicMock()
        _adapter(client).set_user_enabled("x@y.z", False)
        client.admin_disable_user.assert_called_once()

    def test_user_not_found(self):
        client = MagicMock()
        client.admin_enable_user.side_effect = _err("UserNotFoundException")
        with pytest.raises(UserNotFoundError):
            _adapter(client).set_user_enabled("x@y.z", True)

    def test_not_authorized_maps_to_user_disabled(self):
        client = MagicMock()
        client.admin_disable_user.side_effect = _err("NotAuthorizedException")
        with pytest.raises(UserDisabledError):
            _adapter(client).set_user_enabled("x@y.z", False)

    def test_unknown_error_reraises(self):
        client = MagicMock()
        client.admin_enable_user.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).set_user_enabled("x@y.z", True)


class TestSetUserRole:
    def test_same_role_is_noop(self):
        client = MagicMock()
        _adapter(client).set_user_role("x@y.z", "EJEC", "EJEC")
        client.admin_add_user_to_group.assert_not_called()

    def test_role_change_adds_and_removes(self):
        client = MagicMock()
        _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")
        client.admin_add_user_to_group.assert_called_once()
        client.admin_remove_user_from_group.assert_called_once()

    def test_add_group_missing_raises_runtime(self):
        client = MagicMock()
        client.admin_add_user_to_group.side_effect = _err("ResourceNotFoundException")
        with pytest.raises(RuntimeError):
            _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")

    def test_add_user_not_found(self):
        client = MagicMock()
        client.admin_add_user_to_group.side_effect = _err("UserNotFoundException")
        with pytest.raises(UserNotFoundError):
            _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")

    def test_add_unknown_error_reraises(self):
        client = MagicMock()
        client.admin_add_user_to_group.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")

    def test_remove_missing_group_is_ignored(self):
        client = MagicMock()
        client.admin_remove_user_from_group.side_effect = _err("ResourceNotFoundException")
        _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")

    def test_remove_unknown_reraises(self):
        client = MagicMock()
        client.admin_remove_user_from_group.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).set_user_role("x@y.z", "EJEC", "ADMIN")


class TestStartForgotPassword:
    def test_success(self):
        client = MagicMock()
        _adapter(client).start_forgot_password("X@Y.Z")
        client.forgot_password.assert_called_once()

    def test_user_not_found_silent(self):
        client = MagicMock()
        client.forgot_password.side_effect = _err("UserNotFoundException")
        _adapter(client).start_forgot_password("x@y.z")

    def test_limit_exceeded(self):
        client = MagicMock()
        client.forgot_password.side_effect = _err("LimitExceededException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).start_forgot_password("x@y.z")

    def test_not_authorized(self):
        client = MagicMock()
        client.forgot_password.side_effect = _err("NotAuthorizedException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).start_forgot_password("x@y.z")

    def test_unknown_reraises(self):
        client = MagicMock()
        client.forgot_password.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).start_forgot_password("x@y.z")


class TestConfirmForgotPassword:
    def test_success(self):
        client = MagicMock()
        _adapter(client).confirm_forgot_password("X@Y.Z", "123456", "new")
        client.confirm_forgot_password.assert_called_once()

    def test_code_mismatch(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("CodeMismatchException")
        with pytest.raises(InvalidConfirmationCodeError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_expired_code(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("ExpiredCodeException")
        with pytest.raises(InvalidConfirmationCodeError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_invalid_password(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("InvalidPasswordException", "weak")
        with pytest.raises(InvalidPasswordError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_invalid_parameter_maps_to_invalid_password(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("InvalidParameterException", "bad")
        with pytest.raises(InvalidPasswordError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_user_not_found(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("UserNotFoundException")
        with pytest.raises(UserNotFoundError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_limit_exceeded(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("LimitExceededException")
        with pytest.raises(InvalidCredentialsError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")

    def test_unknown_reraises(self):
        client = MagicMock()
        client.confirm_forgot_password.side_effect = _err("InternalErrorException")
        with pytest.raises(ClientError):
            _adapter(client).confirm_forgot_password("x@y.z", "c", "p")
