import json

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from emporium.config import get_settings
from emporium.db import models
from emporium.db.engine import create_engine, create_session_factory
from emporium.security import SecurityError, verify_customer_token
from emporium.tools.customer_context import (
    _customer_context,
    get_customer_context,
    set_customer_context,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

_LAST_ORDERS_CAP = 10
_SEARCH_RESULTS_CAP = 10

mcp = FastMCP(name="emporio-operational-data")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(get_settings().mcp_db_url)
        _session_factory = create_session_factory(_engine)
    return _session_factory


def _bounded_n(n: int, *, default: int = 3, cap: int = _LAST_ORDERS_CAP) -> int:
    try:
        value = int(n)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, cap))


@mcp.tool()
async def get_customer() -> dict:
    """Return the profile of the customer bound to the current session."""
    context = get_customer_context()
    async with _get_session_factory()() as session:
        row = (
            await session.execute(
                select(models.Customer).where(models.Customer.customer_id == context.customer_id)
            )
        ).scalar_one_or_none()
    if row is None:
        return {"error": "customer not found"}
    return {"customer_id": row.customer_id, "name": row.name, "city": row.city}


@mcp.tool()
async def get_customer_last_orders(n: int = 3) -> dict:
    """Return the current customer's most recent orders, most recent first."""
    context = get_customer_context()
    limit = _bounded_n(n)

    async with _get_session_factory()() as session:
        orders = (
            await session.execute(
                select(models.Order)
                .where(models.Order.customer_id == context.customer_id)
                .order_by(models.Order.order_date.desc(), models.Order.order_id.desc())
                .limit(limit)
            )
        ).scalars().all()

        order_ids = [o.order_id for o in orders]
        items_by_order: dict[int, list[dict]] = {oid: [] for oid in order_ids}
        if order_ids:
            items = (
                await session.execute(
                    select(models.OrderItem, models.Product)
                    .join(models.Product, models.Product.product_id == models.OrderItem.product_id)
                    .where(models.OrderItem.order_id.in_(order_ids))
                )
            ).all()
            for item, product in items:
                items_by_order[item.order_id].append(
                    {
                        "product_id": product.product_id,
                        "name": product.name,
                        "quantity": item.quantity,
                        "unit_price_brl": product.price_brl,
                    }
                )

    return {
        "orders": [
            {
                "order_id": o.order_id,
                "order_date": o.order_date.isoformat() if o.order_date else None,
                "status": o.status,
                "total_brl": o.total_brl,
                "payment_method": o.payment_method,
                "tracking_code": o.tracking_code,
                "estimated_delivery": o.estimated_delivery.isoformat()
                if o.estimated_delivery
                else None,
                "items": items_by_order[o.order_id],
            }
            for o in orders
        ]
    }


@mcp.tool()
async def search_products(keyword: str, limit: int = 5) -> dict:
    """Search the catalog by name or description keyword."""
    bounded = max(1, min(int(limit or 5), _SEARCH_RESULTS_CAP))
    pattern = f"%{keyword}%"

    async with _get_session_factory()() as session:
        rows = (
            await session.execute(
                select(models.Product)
                .where(
                    models.Product.status == "active",
                    (models.Product.name.ilike(pattern))
                    | (models.Product.description.ilike(pattern)),
                )
                .order_by(models.Product.name)
                .limit(bounded)
            )
        ).scalars().all()

    return {
        "products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "price_brl": p.price_brl,
                "stock_quantity": p.stock_quantity,
                "status": p.status,
            }
            for p in rows
        ]
    }


@mcp.tool()
async def get_product(product_id: int) -> dict:
    """Return full details of a single product, including active promotions."""
    async with _get_session_factory()() as session:
        product = (
            await session.execute(
                select(models.Product).where(models.Product.product_id == product_id)
            )
        ).scalar_one_or_none()
        if product is None:
            return {"error": "product not found"}

        category_name = None
        if product.category_id is not None:
            category_name = (
                await session.execute(
                    select(models.Category.name).where(
                        models.Category.category_id == product.category_id
                    )
                )
            ).scalar_one_or_none()

        promotions = (
            await session.execute(
                select(models.Promotion).where(
                    models.Promotion.product_id == product_id,
                    models.Promotion.is_active.is_(True),
                )
            )
        ).scalars().all()

    return {
        "product_id": product.product_id,
        "name": product.name,
        "price_brl": product.price_brl,
        "category": category_name,
        "description": product.description,
        "stock_quantity": product.stock_quantity,
        "status": product.status,
        "specs": product.specs,
        "promotions": [
            {
                "discount_percent": promo.discount_percent,
                "description": promo.description,
            }
            for promo in promotions
        ],
    }


@mcp.tool()
async def get_active_promotions() -> dict:
    """List all currently active promotions across the catalog."""
    async with _get_session_factory()() as session:
        rows = (
            await session.execute(
                select(models.Promotion, models.Product)
                .join(models.Product, models.Product.product_id == models.Promotion.product_id)
                .where(models.Promotion.is_active.is_(True))
                .order_by(models.Promotion.product_id)
            )
        ).all()

    return {
        "promotions": [
            {
                "product_id": product.product_id,
                "product_name": product.name,
                "discount_percent": promo.discount_percent,
                "description": promo.description,
            }
            for promo, product in rows
        ]
    }


class CustomerContextMiddleware:
    """Verifies the signed customer-context token on every MCP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.secret = get_settings().mcp_shared_secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        if not auth.startswith("Bearer "):
            await self._reject(send)
            return

        try:
            context = verify_customer_token(self.secret, auth.removeprefix("Bearer "))
        except SecurityError:
            await self._reject(send)
            return

        token = set_customer_context(context)
        try:
            await self.app(scope, receive, send)
        finally:
            _customer_context.reset(token)

    async def _reject(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps({"detail": "invalid or missing backend context"}).encode(),
            }
        )


def build_app() -> ASGIApp:
    return CustomerContextMiddleware(mcp.streamable_http_app())


def main() -> None:
    import os

    import uvicorn

    port = int(os.environ.get("MCP_PORT", "8000"))
    app = build_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
