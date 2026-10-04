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


async def test_list_promotions_returns_all(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.list_promotions()

    assert {p["product_id"] for p in result["promotions"]} == {90, 94, 121, 127}


async def test_search_products_applies_active_promotion(engine, session_factory) -> None:
    """A product lookup returns the discounted final price automatically."""
    await _prepare(engine, session_factory)

    result = await mcp_server.search_products("Crafter HT-100")
    product = next(
        p for p in result["products"] if p["name"] == "Crafter HT-100 Folk Aço Natural"
    )

    assert product["original_price_brl"] == 2399.0
    assert product["final_price_brl"] == 1967.18
    assert product["on_promotion"] is True
    assert product["in_stock"] is True
    assert product["product_id"] == 90
    assert "stock_quantity" not in product
    assert "status" not in product


async def test_search_products_without_promotion_keeps_full_price(
    engine, session_factory
) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.search_products("Yamaha C40")
    product = next(p for p in result["products"] if p["name"] == "Yamaha C40 Nylon Natural")

    assert product["original_price_brl"] == 599.9
    assert product["final_price_brl"] == 599.9
    assert product["on_promotion"] is False


async def test_search_products_never_returns_inactive(engine, session_factory) -> None:
    """Discontinued products are excluded even when the keyword matches."""
    await _prepare(engine, session_factory)

    result = await mcp_server.search_products("Shelby SN-7C")

    assert result["products"] == []


async def test_get_product_applies_active_promotion(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    product = await mcp_server.get_product(94)

    assert product["original_price_brl"] == 5999.0
    assert product["final_price_brl"] == 5519.08
    assert product["on_promotion"] is True
    assert product["in_stock"] is True
    assert "stock_quantity" not in product
    assert "product_id" not in product
    assert "status" not in product
    assert product["promotions"][0]["final_price_brl"] == 5519.08


async def test_get_product_rejects_inactive(engine, session_factory) -> None:
    """An inactive (discontinued) product is treated as not found."""
    await _prepare(engine, session_factory)

    assert await mcp_server.get_product(113) == {"error": "product not found"}


async def test_list_categories_returns_all(engine, session_factory) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.list_categories()

    names = {c["name"] for c in result["categories"]}
    assert names == {
        "Guitarras",
        "Baixos",
        "Baterias e Percussão",
        "Teclados e Pianos",
        "Violões",
        "Instrumentos de Sopro (Madeiras)",
        "Instrumentos de Sopro (Metais)",
        "Cordas Orquestrais",
        "Ukuleles",
    }
    assert all("description" in c for c in result["categories"])
    assert all("category_id" not in c for c in result["categories"])


async def test_list_products_by_category_returns_active_only(
    engine, session_factory
) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.list_products_by_category("Violões", limit=10)

    names = {p["name"] for p in result["products"]}
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in names
    assert all(
        {"product_id", "name", "original_price_brl", "final_price_brl", "on_promotion", "in_stock"}
        <= set(p)
        for p in result["products"]
    )
    assert all("status" not in p and "stock_quantity" not in p for p in result["products"])


async def test_list_products_by_category_sorted_by_price_desc(
    engine, session_factory
) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.list_products_by_category("Violões", limit=10)

    prices = [p["original_price_brl"] for p in result["products"]]
    assert prices == sorted(prices, reverse=True)


async def test_list_products_by_category_rejects_unknown_name(
    engine, session_factory
) -> None:
    await _prepare(engine, session_factory)

    result = await mcp_server.list_products_by_category("Não Existe")

    assert result["error"] == "category not found"
    assert "Violões" in result["categories"]
