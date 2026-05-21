from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.adapters.dynamo_user_repository import DynamoUserRepository
from src.domain.ports import UserNotFoundError
from src.domain.user import User

pytestmark = pytest.mark.unit


def _resource(table: MagicMock) -> MagicMock:
    resource = MagicMock()
    resource.Table.return_value = table
    return resource


def _user(user_id: str = "u-1") -> User:
    base = User.new("sub-1", "x@example.com", "X", "EJEC")
    return User(
        user_id=user_id,
        cognito_sub=base.cognito_sub,
        email=base.email,
        full_name=base.full_name,
        role=base.role,
        is_active=base.is_active,
        created_at=base.created_at,
        updated_at=base.updated_at,
    )


def _conditional_error() -> ClientError:
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")


def _other_error() -> ClientError:
    return ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem")


class TestDynamoUserRepository:
    def test_save_if_absent_ok(self):
        table = MagicMock()
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.save_if_absent(_user()) is True
        table.put_item.assert_called_once()

    def test_save_if_absent_returns_false_on_conflict(self):
        table = MagicMock()
        table.put_item.side_effect = _conditional_error()
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.save_if_absent(_user()) is False

    def test_save_if_absent_reraises_unknown(self):
        table = MagicMock()
        table.put_item.side_effect = _other_error()
        repo = DynamoUserRepository("t", resource=_resource(table))
        with pytest.raises(ClientError):
            repo.save_if_absent(_user())

    def test_find_by_email_returns_user(self):
        table = MagicMock()
        u = _user()
        table.query.return_value = {
            "Items": [
                {
                    "user_id": u.user_id,
                    "cognito_sub": u.cognito_sub,
                    "email": u.email,
                    "full_name": u.full_name,
                    "role": u.role,
                    "is_active": True,
                    "created_at": u.created_at,
                    "updated_at": u.updated_at,
                }
            ]
        }
        repo = DynamoUserRepository("t", resource=_resource(table))
        found = repo.find_by_email("X@Example.com")
        assert found is not None
        assert found.user_id == u.user_id

    def test_find_by_email_returns_none_when_empty(self):
        table = MagicMock()
        table.query.return_value = {"Items": []}
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.find_by_email("x@example.com") is None

    def test_exists_by_email(self):
        table = MagicMock()
        table.query.return_value = {"Items": []}
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.exists_by_email("x@example.com") is False

    def test_get_by_id_returns_user(self):
        table = MagicMock()
        u = _user()
        table.get_item.return_value = {
            "Item": {
                "user_id": u.user_id,
                "cognito_sub": u.cognito_sub,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": True,
                "created_at": u.created_at,
            }
        }
        repo = DynamoUserRepository("t", resource=_resource(table))
        found = repo.get_by_id(u.user_id)
        assert found is not None
        assert found.updated_at == u.created_at

    def test_get_by_id_returns_none_when_missing(self):
        table = MagicMock()
        table.get_item.return_value = {}
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.get_by_id("u-x") is None

    def test_list_all(self):
        table = MagicMock()
        u = _user()
        table.scan.return_value = {
            "Items": [
                {
                    "user_id": u.user_id,
                    "cognito_sub": u.cognito_sub,
                    "email": u.email,
                    "full_name": u.full_name,
                    "role": u.role,
                    "is_active": True,
                    "created_at": u.created_at,
                    "updated_at": u.updated_at,
                }
            ]
        }
        repo = DynamoUserRepository("t", resource=_resource(table))
        users = repo.list_all(limit=10)
        assert len(users) == 1

    def test_update_ok(self):
        table = MagicMock()
        repo = DynamoUserRepository("t", resource=_resource(table))
        assert repo.update(_user()) is not None

    def test_update_raises_when_missing(self):
        table = MagicMock()
        table.put_item.side_effect = _conditional_error()
        repo = DynamoUserRepository("t", resource=_resource(table))
        with pytest.raises(UserNotFoundError):
            repo.update(_user())

    def test_update_reraises_unknown_error(self):
        table = MagicMock()
        table.put_item.side_effect = _other_error()
        repo = DynamoUserRepository("t", resource=_resource(table))
        with pytest.raises(ClientError):
            repo.update(_user())
