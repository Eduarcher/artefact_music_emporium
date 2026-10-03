import asyncio
import logging

import httpx

from emporium.config import get_settings

logger = logging.getLogger("emporium.warmup")

_KEEP_ALIVE = "24h"
_WARMUP_TIMEOUT = 300.0


async def _warm_generate(client: httpx.AsyncClient, model: str, keep_alive: str) -> None:
    resp = await client.post(
        "/api/generate",
        json={
            "model": model,
            "prompt": "ok",
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"num_predict": 1},
        },
    )
    resp.raise_for_status()


async def _warm_embed(client: httpx.AsyncClient, model: str, keep_alive: str) -> None:
    resp = await client.post(
        "/api/embed",
        json={"model": model, "input": "ok", "keep_alive": keep_alive},
    )
    resp.raise_for_status()


async def main() -> None:
    """Preload the local generation and embedding models into Ollama memory.

    Runs after the models are pulled so the first customer message does not pay
    the one-time model load. Hosted-only defaults are skipped.
    """
    settings = get_settings()
    default_model = settings.default_model
    if not default_model.startswith("ollama/"):
        logger.info("default model %s is hosted; nothing to warm up", default_model)
        return

    generate_model = default_model.removeprefix("ollama/")
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url, timeout=_WARMUP_TIMEOUT
    ) as client:
        await _warm_generate(client, generate_model, _KEEP_ALIVE)
        logger.info("warmed generation model %s", generate_model)
        await _warm_embed(client, settings.embedding_model, _KEEP_ALIVE)
        logger.info("warmed embedding model %s", settings.embedding_model)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
