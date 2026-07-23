import asyncio
import hashlib
import uuid
from langgraph_sdk import get_client

payload = {
    "text": (
        "The Apollo 11 mission was a major success for NASA. It was the first mission to land humans on the Moon. "
        "Neil Armstrong and Buzz Aldrin walked on the lunar surface on July 20, 1969. This was truly amazing. "
        "They collected samples of lunar material and returned safely to Earth. Some say it changed humanity. "
        "The mission also deployed several scientific instruments on the Moon. Its impact is undeniable."
    ),
    "metadata": "NASA Historical Archives - Apollo 11 Mission Report Summary",
}


async def main():
    client = get_client(url="http://127.0.0.1:2024")

    thread_id = str(
        uuid.UUID(hex=hashlib.md5(payload["metadata"].encode("UTF-8")).hexdigest())
    )

    try:
        await client.threads.delete(thread_id)
    except:  # noqa: E722
        pass

    await client.threads.create(thread_id=thread_id)
    await client.runs.create(
        thread_id=thread_id,
        assistant_id="claim_extractor",
        input=payload,
    )


if __name__ == "__main__":
    asyncio.run(main())
