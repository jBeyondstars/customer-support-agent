import psycopg
import pytest
from fastapi.testclient import TestClient

from support_agent.api.main import app
from support_agent.config import get_settings
from support_agent.db import get_checkpointer, get_pool


@pytest.fixture
def conn():
    """Connection to the seeded dev database. Everything a test writes is rolled back."""
    try:
        conn = psycopg.connect(get_settings().database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running, start it with: docker compose up -d db")
    with conn, conn.transaction(force_rollback=True):
        yield conn


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def login(client):
    def headers_for(customer_id: int) -> dict:
        response = client.post("/auth/demo-login", json={"customer_id": customer_id})
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return headers_for


@pytest.fixture
def new_thread(conn, client, login):
    """Creates conversations through the API and deletes them afterwards."""
    created = []

    def make(customer_id: int) -> str:
        thread_id = client.post("/threads", headers=login(customer_id)).json()["thread_id"]
        created.append(thread_id)
        return thread_id

    yield make

    with get_pool().connection() as cleanup:
        cleanup.execute("delete from threads where id = any(%s)", (created,))
    for thread_id in created:
        get_checkpointer().delete_thread(thread_id)
