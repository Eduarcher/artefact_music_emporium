import pytest

from emporium.ingest.csv_ingest import ingest_csv
from emporium.security import (
    CustomerContext,
    SecurityError,
    sign_customer_token,
    verify_customer_token,
)
from emporium.tools import customer_context, mcp_server

from .conftest import RAW_DATA_DIR

_SECRET = "test-secret"


def test_token_roundtrip_and_rejection() -> None:
    token = sign_customer_token(
        _SECRET, customer_id=3, session_id="s1", ttl_seconds=60
    )
    context = verify_customer_token(_SECRET, token)
    assert context.customer_id == 3
    assert context.session_id == "s1"

    with pytest.raises(SecurityError):
        verify_customer_token("wrong-secret", token)

    with pytest.raises(SecurityError):
        verify_customer_token(_SECRET, token + "tampered")

    expired = sign_customer_token(_SECRET, customer_id=3, session_id="s1", ttl_seconds=-1)
    with pytest.raises(SecurityError):
        verify_customer_token(_SECRET, expired)


async def test_customer_tools_are_isolated(engine, session_factory) -> None:
    await ingest_csv(engine, RAW_DATA_DIR)

    mcp_server._engine = engine
    mcp_server._session_factory = session_factory

    token_a = customer_context.set_customer_context(
        CustomerContext(customer_id=3, session_id="a", expires_at=0)
    )
    profile_a = await mcp_server.get_customer()
    orders_a = await mcp_server.get_customer_last_orders(10)
    customer_context._customer_context.reset(token_a)

    token_b = customer_context.set_customer_context(
        CustomerContext(customer_id=7, session_id="b", expires_at=0)
    )
    profile_b = await mcp_server.get_customer()
    orders_b = await mcp_server.get_customer_last_orders(10)
    customer_context._customer_context.reset(token_b)

    assert profile_a["name"] != profile_b["name"]
    assert "customer_id" not in profile_a
    assert {"name", "city"} <= set(profile_a)

    order_ids_a = {o["order_id"] for o in orders_a["orders"]}
    order_ids_b = {o["order_id"] for o in orders_b["orders"]}

    assert order_ids_a == {19, 1}
    assert order_ids_b == {20, 2}
    assert order_ids_a.isdisjoint(order_ids_b)


async def test_customer_tool_requires_bound_context() -> None:
    customer_context._customer_context.set(None)
    with pytest.raises(PermissionError):
        await mcp_server.get_customer()


async def test_order_status_translated_and_cancellation_reason(
    engine, session_factory
) -> None:
    await ingest_csv(engine, RAW_DATA_DIR)
    mcp_server._engine = engine
    mcp_server._session_factory = session_factory

    token = customer_context.set_customer_context(
        CustomerContext(customer_id=3, session_id="a", expires_at=0)
    )
    orders = await mcp_server.get_customer_last_orders(10)
    customer_context._customer_context.reset(token)

    by_id = {o["order_id"]: o for o in orders["orders"]}
    assert by_id[19]["status"] == "Cancelado"
    assert by_id[19]["cancellation_reason"] == "Pagamento não confirmado dentro do prazo"
    assert by_id[1]["status"] == "Entregue"
    assert by_id[1]["cancellation_reason"] is None
