import redis.asyncio as redis
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph_sdk import Auth
from utils.settings import settings
from security.api_keys import API_KEY_PREFIX

auth = Auth()

BEARER_SCHEME = "bearer"


@asynccontextmanager
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Redis client context manager for proper connection handling."""
    client = redis.from_url(str(settings.redis_uri))
    try:
        yield client
    finally:
        await client.aclose()


async def _verify_api_key(api_key: str) -> bool:
    """Verify API key exists in Redis."""
    try:
        async with redis_client() as client:
            return bool(await client.exists(f"{API_KEY_PREFIX}{api_key}"))
    except redis.RedisError:
        return False


def _parse_authorization(authorization: str) -> str:
    """Parse and validate authorization header, returning the token."""
    try:
        scheme, token = authorization.split(maxsplit=1)
    except ValueError:
        raise Auth.exceptions.HTTPException(401, "Invalid authorization format")

    if scheme.lower() != BEARER_SCHEME:
        raise Auth.exceptions.HTTPException(401, "Invalid authorization scheme")

    if not token:
        raise Auth.exceptions.HTTPException(401, "Missing API key")

    return token


@auth.authenticate
async def get_current_user(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Authenticate user via API key stored in Redis."""
    if not authorization:
        raise Auth.exceptions.HTTPException(401, "Missing authorization header")

    token = _parse_authorization(authorization)

    if not await _verify_api_key(token):
        raise Auth.exceptions.HTTPException(401, "Invalid API key")

    return {"identity": f"{API_KEY_PREFIX}{token[:8]}..."}
