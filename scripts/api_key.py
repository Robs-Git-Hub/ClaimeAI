#!/usr/bin/env python3
"""CLI tool for API key management using Redis for LangGraph proxy authentication."""

import asyncio
import sys
from typing import Optional

from security.api_keys import (
    generate_secure_api_key,
    get_api_keys,
    revoke_api_key,
    store_api_key,
)
from utils.redis import test_redis_connection


def print_usage() -> None:
    """Print usage information."""
    print("""
    🔐 ClaimeAI API Key Manager

    Usage:
        python api_key.py generate [description]  - Generate new API key
        python api_key.py list                   - List all API keys
        python api_key.py revoke <api_key>       - Revoke an API key
        python api_key.py test                   - Test Redis connection

    Examples:
        python api_key.py generate "Production API key"
        python api_key.py generate "Development testing"
        python api_key.py revoke abc123xyz789
    """)


async def handle_generate(description: Optional[str] = None) -> None:
    """Handle API key generation."""
    if not await test_redis_connection():
        print(
            "⚠️  Please ensure Redis is running and REDIS_URI is correctly configured."
        )
        return

    api_key = generate_secure_api_key()
    await store_api_key(api_key, description or "Generated API key")

    print("✅ API key stored successfully!")
    print(f"🔑 Key: {api_key}")
    print(f"📝 Description: {description or 'Generated API key'}")
    print("\n🚀 To use this API key, include it in your requests:")
    print(f"   Authorization: Bearer {api_key}")


async def handle_list() -> None:
    """Handle listing API keys."""
    api_keys = await get_api_keys()

    if not api_keys:
        print("📭 No API keys found in Redis.")
        return

    print(f"📋 Found {len(api_keys)} API key(s):")
    print("-" * 60)

    for key_data in api_keys:
        print(f"🔑 Key: {key_data['key']}")
        print(f"📝 Description: {key_data['description']}")
        print(f"📅 Created: {key_data['created_at']}")
        print(f"✅ Active: {key_data['active']}")
        print("-" * 60)


async def handle_revoke(api_key: str) -> None:
    """Handle API key revocation."""
    if await revoke_api_key(api_key):
        print(f"✅ API key '{api_key}' has been revoked.")
    else:
        print(f"❌ API key '{api_key}' not found.")


async def handle_test() -> None:
    """Handle Redis connection test."""
    if await test_redis_connection():
        print("✅ Redis connection successful!")
    else:
        print("❌ Redis connection failed!")


async def ensure_redis_connection(command_func, *args) -> None:
    """Ensure Redis connection before executing command."""
    if not await test_redis_connection():
        print(
            "⚠️  Please ensure Redis is running and REDIS_URI is correctly configured."
        )
        return
    await command_func(*args)


async def main() -> None:
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].lower()

    try:
        if command == "generate":
            description = sys.argv[2] if len(sys.argv) > 2 else None
            await handle_generate(description)

        elif command == "list":
            await ensure_redis_connection(handle_list)

        elif command == "revoke":
            if len(sys.argv) < 3:
                print("❌ Please provide an API key to revoke.")
                print("Usage: python api_key.py revoke <api_key>")
                return
            await ensure_redis_connection(handle_revoke, sys.argv[2])

        elif command == "test":
            await handle_test()

        else:
            print(f"❌ Unknown command: {command}")
            print_usage()

    except Exception as e:
        print(f"❌ Error executing command '{command}': {e}")


if __name__ == "__main__":
    asyncio.run(main())
