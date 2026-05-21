from __future__ import annotations
import pytest
from src.domain.services import ListUsersService

pytestmark = pytest.mark.unit

@pytest.fixture
def service(repo):
    return ListUsersService(repo=repo)


class TestListUsers:
    def test_devuelve_lista_vacia_si_no_hay_usuarios(self, service):
        assert service.list() == []

    def test_devuelve_todos_los_usuarios(self, service, repo, make_user):
        u1 = repo.seed(make_user(email="a@example.com", cognito_sub="s1"))
        u2 = repo.seed(make_user(email="b@example.com", cognito_sub="s2"))
        result = service.list()
        assert set(result) == {u1, u2}

    def test_respeta_el_limit(self, service, repo, make_user):
        for i in range(5):
            repo.seed(make_user(email=f"u{i}@example.com", cognito_sub=f"s{i}"))
        assert len(service.list(limit=2)) == 2
