from emporium.ingest.csv_ingest import ingest_csv
from emporium.tools import mcp_server

from .conftest import RAW_DATA_DIR


async def _prepare(engine, session_factory) -> None:
    await ingest_csv(engine, RAW_DATA_DIR)
    mcp_server._engine = engine
    mcp_server._session_factory = session_factory


async def test_search_promotions_filters_by_category(engine, session_factory) -> None:
    """A category query returns only promotions for that category."""
    await _prepare(engine, session_factory)

    result = await mcp_server.search_promotions("violão")
    product_ids = {p["product_id"] for p in result["promotions"]}

    assert product_ids == {90, 94}
    assert all(p["category"] == "Violões" for p in result["promotions"])


async def test_search_promotions_matches_description(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.search_promotions("ukulele")
    product_ids = {p["product_id"] for p in result["promotions"]}

    assert product_ids == {121, 127}


async def test_search_promotions_returns_empty_when_unrelated(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.search_promotions("teclado")

    assert result["promotions"] == []


async def test_get_active_promotions_returns_all(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.get_active_promotions()

    assert {p["product_id"] for p in result["promotions"]} == {90, 94, 121, 127}
