"""API key management utilities for generation, storage, and validation."""

import secrets
import string
from datetime import datetime

from utils.redis import redis_client

# Constants
API_KEY_LENGTH = 32
API_KEY_PREFIX = "api_key:"
API_KEYS_SET = "api_keys"
ALPHABET = string.ascii_letters + string.digits


def generate_secure_api_key(length: int = API_KEY_LENGTH) -> str:
    """Generate a cryptographically secure API key."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def store_api_key(api_key: str, description: str = "") -> None:
    """Store API key in Redis with metadata."""
    async with redis_client() as client:
        key_data = {
            "created_at": datetime.now().isoformat(),
            "description": description,
            "active": "true",
        }

        await client.hset(f"{API_KEY_PREFIX}{api_key}", mapping=key_data)
        await client.sadd(API_KEYS_SET, api_key)


async def get_api_keys() -> list[dict]:
    """Get all stored API keys with their metadata."""
    async with redis_client() as client:
        api_keys = await client.smembers(API_KEYS_SET)

        if not api_keys:
            return []

        keys_data = []
        for api_key in api_keys:
            key_str = api_key.decode()
            key_data = await client.hgetall(f"{API_KEY_PREFIX}{key_str}")

            if key_data:
                keys_data.append(
                    {
                        "key": key_str,
                        "description": key_data.get(b"description", b"").decode(),
                        "created_at": key_data.get(b"created_at", b"").decode(),
                        "active": key_data.get(b"active", b"").decode(),
                    }
                )

        return keys_data


async def revoke_api_key(api_key: str) -> bool:
    """Revoke an API key by removing it from Redis. Returns True if key existed."""
    async with redis_client() as client:
        if not await client.exists(f"{API_KEY_PREFIX}{api_key}"):
            return False

        await client.delete(f"{API_KEY_PREFIX}{api_key}")
        await client.srem(API_KEYS_SET, api_key)
        return True


async def validate_api_key(api_key: str) -> bool:
    """Validate if an API key exists and is active."""
    async with redis_client() as client:
        key_data = await client.hgetall(f"{API_KEY_PREFIX}{api_key}")
        return bool(key_data and key_data.get(b"active") == b"true")
