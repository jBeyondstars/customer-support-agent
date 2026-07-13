from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DemoLogin(BaseModel):
    customer_id: int


class NewMessage(BaseModel):
    # The cap keeps a single message from costing a fortune in tokens.
    content: str = Field(min_length=1, max_length=2000)


class Confirmation(BaseModel):
    approved: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Me(BaseModel):
    customer_id: int
    first_name: str


class Source(BaseModel):
    title: str
    section: str
    document: str


class ChatMessage(BaseModel):
    role: Literal["customer", "assistant"]
    content: str
    sources: list[Source] = []


class PendingAction(BaseModel):
    name: str
    args: dict[str, Any]


class ThreadSummary(BaseModel):
    thread_id: str
    created_at: datetime


class Thread(BaseModel):
    thread_id: str
    messages: list[ChatMessage]
    pending: list[PendingAction] = []
