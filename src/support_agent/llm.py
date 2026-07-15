from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from support_agent.config import get_settings


@lru_cache
def get_embeddings() -> Embeddings:
    return init_embeddings(get_settings().embedding_model)


@lru_cache
def get_chat_model(name: str | None = None, streaming: bool = True) -> BaseChatModel:
    return init_chat_model(name or get_settings().chat_model, disable_streaming=not streaming)
