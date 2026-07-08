from fastapi import FastAPI, HTTPException

from support_agent.api.auth import CustomerId, create_token
from support_agent.api.schemas import DemoLogin, Me, Token
from support_agent.db import get_pool

app = FastAPI(title="Nomad Cycles support agent")


@app.get("/health")
def health() -> dict:
    with get_pool().connection() as conn:
        conn.execute("select 1")
    return {"status": "ok"}


@app.post("/auth/demo-login")
def demo_login(body: DemoLogin) -> Token:
    """Stand-in for a real login: anyone can be any customer. It exists so the demo
    can switch accounts, everything after it goes through the token like it would
    with a real identity provider."""
    if first_name(body.customer_id) is None:
        raise HTTPException(404, "Unknown customer")
    return Token(access_token=create_token(body.customer_id))


@app.get("/me")
def me(customer_id: CustomerId) -> Me:
    name = first_name(customer_id)
    if name is None:
        raise HTTPException(401, "Unknown customer")
    return Me(customer_id=customer_id, first_name=name)


def first_name(customer_id: int) -> str | None:
    with get_pool().connection() as conn:
        row = conn.execute("select first_name from customers where id = %s", (customer_id,))
        found = row.fetchone()
    return found[0] if found else None
