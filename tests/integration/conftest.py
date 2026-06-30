import psycopg
import pytest

from support_agent.config import get_settings


@pytest.fixture
def conn():
    """Connection to the seeded dev database. Everything a test writes is rolled back."""
    try:
        conn = psycopg.connect(get_settings().database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running, start it with: docker compose up -d db")
    with conn, conn.transaction(force_rollback=True):
        yield conn
