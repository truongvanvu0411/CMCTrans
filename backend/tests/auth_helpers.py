from __future__ import annotations

from fastapi.testclient import TestClient


def authenticate_client(
    client: TestClient,
    *,
    username: str = "admin",
    password: str = "admin123!",
) -> dict[str, object]:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    client.headers.update({"Authorization": f"Bearer {payload['session_token']}"})
    return payload
