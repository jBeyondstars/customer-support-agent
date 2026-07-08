from pydantic import BaseModel


class DemoLogin(BaseModel):
    customer_id: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Me(BaseModel):
    customer_id: int
    first_name: str
