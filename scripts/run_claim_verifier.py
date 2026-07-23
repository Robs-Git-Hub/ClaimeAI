import asyncio
import hashlib
import uuid
from langgraph_sdk import get_client

payload = {
    "claim": "Neil Armstrong and Buzz Aldrin were the first humans to walk on the Moon on July 20, 1969.",
    "context": "Apollo 11 mission historical verification",
}


async def main():
    client = get_client(url="http://127.0.0.1:2024")

    thread_id = str(
        uuid.UUID(hex=hashlib.md5(payload["context"].encode("UTF-8")).hexdigest())
    )

    try:
        await client.threads.delete(thread_id)
    except:  # noqa: E722
        pass

    await client.threads.create(thread_id=thread_id)
    await client.runs.create(
        thread_id=thread_id,
        assistant_id="claim_verifier",
        input=payload,
    )


if __name__ == "__main__":
    asyncio.run(main())
