from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from emporium.db.models import Base


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
