from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    """Per-run data set by the API from the auth token. Tools read it, the model never sees it."""

    customer_id: int
