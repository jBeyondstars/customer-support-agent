from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from support_agent.config import get_settings

ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(hours=12)

bearer = HTTPBearer(auto_error=False)


def create_token(customer_id: int) -> str:
    payload = {"sub": str(customer_id), "exp": datetime.now(UTC) + TOKEN_LIFETIME}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def current_customer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> int:
    if credentials is None:
        raise HTTPException(401, "Missing bearer token")
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret, algorithms=[ALGORITHM]
        )
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired token") from None
    return int(payload["sub"])


# The only way an endpoint gets a customer id. It never comes from the request body.
CustomerId = Annotated[int, Depends(current_customer)]
