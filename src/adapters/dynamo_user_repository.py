from typing import Optional, Sequence
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from src.domain.ports import UserNotFoundError, UserRepository
from src.domain.user import User


class DynamoUserRepository(UserRepository):

    def __init__(self, table_name: str, resource=None):
        self._table = (resource or boto3.resource("dynamodb")).Table(table_name)

    # Helpers 
    @staticmethod
    def _to_item(user: User) -> dict:
        return {
            "user_id": user.user_id,
            "cognito_sub": user.cognito_sub,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    @staticmethod
    def _from_item(item: dict) -> User:
        return User(
            user_id=item["user_id"],
            cognito_sub=item["cognito_sub"],
            email=item["email"],
            full_name=item["full_name"],
            role=item["role"],
            is_active=bool(item["is_active"]),
            created_at=item["created_at"],
            updated_at=item.get("updated_at", item["created_at"]),
        )

    # UserRepository 
    def save_if_absent(self, user: User) -> bool:
        try:
            self._table.put_item(
                Item=self._to_item(user),
                ConditionExpression="attribute_not_exists(user_id)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def exists_by_email(self, email: str) -> bool:
        return self.find_by_email(email) is not None

    def find_by_email(self, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        resp = self._table.query(
            IndexName="by_email",
            KeyConditionExpression=Key("email").eq(normalized),
            Limit=1,
        )
        items = resp.get("Items") or []
        return self._from_item(items[0]) if items else None

    def get_by_id(self, user_id: str) -> Optional[User]:
        resp = self._table.get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        return self._from_item(item) if item else None

    def list_all(self, limit: int = 100) -> Sequence[User]:
        resp = self._table.scan(Limit=limit)
        return [self._from_item(it) for it in resp.get("Items", [])]

    def update(self, user: User) -> User:
        try:
            self._table.put_item(
                Item=self._to_item(user),
                ConditionExpression="attribute_exists(user_id)",
            )
            return user
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise UserNotFoundError(f"Usuario {user.user_id} no existe")
            raise
