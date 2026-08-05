"""Tests for the /users endpoints.

The backend's user endpoints delegate all data access to `app_backend.database`.
These tests patch that module at the point it is imported by `app_backend.main`,
replacing each coroutine with an AsyncMock so no real SQLite file is needed.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app_backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

def test_list_users(client: TestClient):
    mock_users = {
        "u_1": {"name": "User One", "email": "one@example.com"},
        "u_2": {"name": "User Two", "email": "two@example.com"},
    }
    with patch("app_backend.main.database.get_all_users", new=AsyncMock(return_value=mock_users)):
        response = client.get("/users")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    data.sort(key=lambda x: x["id"])
    assert data[0]["id"] == "u_1"
    assert data[0]["name"] == "User One"
    assert data[1]["id"] == "u_2"
    assert data[1]["name"] == "User Two"


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------

def test_get_user_detail_success(client: TestClient):
    mock_user = {"name": "User One", "email": "one@example.com"}
    with patch("app_backend.main.database.get_user", new=AsyncMock(return_value=mock_user)):
        response = client.get("/users/u_1")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "u_1"
    assert data["data"]["name"] == "User One"


def test_get_user_detail_not_found(client: TestClient):
    with patch("app_backend.main.database.get_user", new=AsyncMock(return_value=None)):
        response = client.get("/users/u_nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

def test_save_user_new(client: TestClient):
    mock_save = AsyncMock(return_value=None)
    with patch("app_backend.main.database.save_user", new=mock_save):
        response = client.post("/users", json={"id": "u_3", "data": {"name": "User Three", "role": "admin"}})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["id"] == "u_3"

    mock_save.assert_called_once()
    call_args = mock_save.call_args
    # positional: (db_path, user_id, data)
    assert call_args.args[1] == "u_3"
    assert call_args.args[2]["name"] == "User Three"
