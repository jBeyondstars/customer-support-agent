from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Provider SDKs (openai, anthropic, mistral...) read their API keys from the
# environment, so .env has to end up in os.environ, not just in Settings.
load_dotenv()


class Settings(BaseSettings):
    database_url: str = "postgresql://support:support@localhost:5433/support"
    chat_model: str = "openai:gpt-6-luna"
    judge_model: str = "openai:gpt-6.1-sol"
    embedding_model: str = "text-embedding-3-small"
    jwt_secret: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
