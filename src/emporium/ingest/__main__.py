import asyncio
import logging

from emporium.config import get_settings
from emporium.db.engine import create_engine
from emporium.db.init_db import init_db
from emporium.ingest.csv_ingest import ingest_csv
from emporium.ingest.pdf_ingest import ingest_policy
from emporium.rag.embedder import build_embedder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("emporium.ingest")


async def main() -> None:
    settings = get_settings()
    engine = create_engine()
    try:
        await init_db(engine)
        csv_counts = await ingest_csv(engine, settings.raw_data_dir)
        logger.info("CSV ingestion complete: %s", csv_counts)

        embedder = build_embedder()
        policy_result = await ingest_policy(engine, embedder, settings.raw_data_dir)
        logger.info("Policy ingestion complete: %s", policy_result)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
