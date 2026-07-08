from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from support_agent.api.main import app
from support_agent.config import get_settings

pytestmark = pytest.mark.integration

client = TestClient(app)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_gives_a_token_that_identifies_the_customer(conn):
    token = client.post("/auth/demo-login", json={"customer_id": 2}).json()["access_token"]

    response = client.get("/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {"customer_id": 2, "first_name": "Lucas"}


def test_unknown_customer_cannot_log_in(conn):
    assert client.post("/auth/demo-login", json={"customer_id": 9999}).status_code == 404


@pytest.mark.parametrize(
    "headers",
    [
        {},
        bearer("not-a-jwt"),
        bearer(jwt.encode({"sub": "1"}, "someone-elses-secret-that-is-long-enough", "HS256")),
        bearer(
            jwt.encode(
                {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
                get_settings().jwt_secret,
                "HS256",
            )
        ),
    ],
    ids=["missing", "garbage", "wrong-secret", "expired"],
)
def test_bad_tokens_are_rejected(conn, headers):
    assert client.get("/me", headers=headers).status_code == 401
