from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Provider SDKs (openai, anthropic, mistral...) read their API keys from the
# environment, so .env has to end up in os.environ, not just in Settings.
load_dotenv()


class Settings(BaseSettings):
    # A line left blank in .env ("JWT_SECRET=") falls back to the default.
    model_config = SettingsConfigDict(env_ignore_empty=True)

    database_url: str = "postgresql://support:support@localhost:55432/support"
    chat_model: str = "openai:gpt-6-luna"
    judge_model: str = "openai:gpt-6.1-sol"
    embedding_model: str = "openai:text-embedding-3-small"
    jwt_secret: str = Field("local-dev-secret-do-not-use-anywhere-else", min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()
