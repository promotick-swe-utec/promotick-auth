from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("USERS_TABLE_NAME", "test-users")
os.environ.setdefault("USER_POOL_ID", "test-pool")
os.environ.setdefault("USER_POOL_CLIENT_ID", "test-client")
os.environ.setdefault("AUDIT_LOGS_TABLE_NAME", "test-audit")
os.environ.setdefault("EMAIL_CHECK_DNS", "false")


@pytest.fixture(autouse=True)
def _stub_boto3(monkeypatch):
    fake_client = MagicMock(name="cognito-client")
    fake_table = MagicMock(name="dynamo-table")
    fake_resource = MagicMock(name="dynamo-resource")
    fake_resource.Table.return_value = fake_table

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **kw: fake_client)
    monkeypatch.setattr(boto3, "resource", lambda *a, **kw: fake_resource)
    yield
