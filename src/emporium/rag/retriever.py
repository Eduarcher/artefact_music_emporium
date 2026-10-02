from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporium.config import get_settings
from emporium.db.models import PolicyChunk


@dataclass(frozen=True)
class RetrievedChunk:
    section: str
    title: str
    text: str
    similarity: float


class PolicyRetriever:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._settings = get_settings()

    async def search(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        settings = self._settings
        k = top_k or settings.policy_top_k
        query_vec = await self._embedder.aembed_query(query)
        max_distance = 1 - settings.policy_similarity_threshold

        stmt = (
            select(
                PolicyChunk,
                (1 - PolicyChunk.embedding.cosine_distance(query_vec)).label("similarity"),
            )
            .where(PolicyChunk.embedding.cosine_distance(query_vec) <= max_distance)
            .order_by(PolicyChunk.embedding.cosine_distance(query_vec))
            .limit(k)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        return [
            RetrievedChunk(
                section=row[0].section,
                title=row[0].title,
                text=row[0].text,
                similarity=float(row[1]),
            )
            for row in rows
        ]
