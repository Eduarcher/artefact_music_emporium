import json

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
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

mcp = FastMCP(
    name="emporio-operational-data",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=get_settings().allowed_mcp_hosts,
    ),
)


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
    """Search the catalog by name or description keyword.

    Each result includes ``final_price_brl``, the price after the best active
    promotion (same as ``price_brl`` when the product is not on promotion), so
    quote the final price directly. ``in_stock`` tells whether the item is
    available; raw stock counts are intentionally not exposed.
    """
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

        promotions = await _active_promotions_by_product(
            session, [p.product_id for p in rows]
        )

    return {
        "products": [
            _product_summary(p, promotions.get(p.product_id, [])) for p in rows
        ]
    }


@mcp.tool()
async def get_product(product_id: int) -> dict:
    """Return full details of a single product, including active promotions.

    ``in_stock`` tells whether the item is available; raw stock counts are
    intentionally not exposed.
    """
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

    final_price = min(
        (_final_price(product.price_brl, promo.discount_percent) for promo in promotions),
        default=product.price_brl,
    )

    return {
        "product_id": product.product_id,
        "name": product.name,
        "price_brl": product.price_brl,
        "final_price_brl": final_price,
        "on_promotion": final_price < product.price_brl,
        "category": category_name,
        "description": product.description,
        "in_stock": product.stock_quantity > 0,
        "status": product.status,
        "specs": product.specs,
        "promotions": [
            {
                "promotion_id": promo.promotion_id,
                "discount_percent": promo.discount_percent,
                "final_price_brl": _final_price(product.price_brl, promo.discount_percent),
                "description": promo.description,
            }
            for promo in promotions
        ],
    }


def _final_price(price_brl: float, discount_percent: float | None) -> float:
    if not discount_percent:
        return price_brl
    return round(price_brl * (1 - discount_percent / 100), 2)


async def _active_promotions_by_product(session, product_ids: list[int]) -> dict[int, list]:
    """Return active promotions grouped by product id, best discount first."""
    grouped: dict[int, list] = {pid: [] for pid in product_ids}
    if not product_ids:
        return grouped

    rows = (
        await session.execute(
            select(models.Promotion)
            .where(
                models.Promotion.product_id.in_(product_ids),
                models.Promotion.is_active.is_(True),
            )
            .order_by(models.Promotion.discount_percent.desc())
        )
    ).scalars().all()
    for promo in rows:
        grouped.setdefault(promo.product_id, []).append(promo)
    return grouped


def _product_summary(product, promotions: list) -> dict:
    """Product fields plus the effective price after the best active promotion."""
    final_price = min(
        (_final_price(product.price_brl, promo.discount_percent) for promo in promotions),
        default=product.price_brl,
    )
    return {
        "product_id": product.product_id,
        "name": product.name,
        "price_brl": product.price_brl,
        "final_price_brl": final_price,
        "on_promotion": final_price < product.price_brl,
        "in_stock": product.stock_quantity > 0,
        "status": product.status,
    }


def _promotion_row(promo, product, category_name: str | None) -> dict:
    return {
        "product_id": product.product_id,
        "product_name": product.name,
        "category": category_name,
        "discount_percent": promo.discount_percent,
        "original_price_brl": product.price_brl,
        "final_price_brl": _final_price(product.price_brl, promo.discount_percent),
        "description": promo.description,
    }


@mcp.tool()
async def search_promotions(keyword: str, limit: int = 5) -> dict:
    """Search active promotions by product name, product description or category.

    Use this for targeted promotion questions, e.g. "promoções de violão" or
    "tem promoção de teclado?". It never returns promotions outside the matching
    products/categories.
    """
    bounded = max(1, min(int(limit or 5), _SEARCH_RESULTS_CAP))
    pattern = f"%{keyword}%"

    async with _get_session_factory()() as session:
        rows = (
            await session.execute(
                select(models.Promotion, models.Product, models.Category.name)
                .join(models.Product, models.Product.product_id == models.Promotion.product_id)
                .outerjoin(
                    models.Category,
                    models.Category.category_id == models.Product.category_id,
                )
                .where(
                    models.Promotion.is_active.is_(True),
                    (models.Product.name.ilike(pattern))
                    | (models.Product.description.ilike(pattern))
                    | (models.Category.name.ilike(pattern)),
                )
                .order_by(models.Product.name)
                .limit(bounded)
            )
        ).all()

    return {
        "promotions": [
            _promotion_row(promo, product, category) for promo, product, category in rows
        ]
    }


@mcp.tool()
async def get_active_promotions() -> dict:
    """List all currently active promotions across the catalog.

    Use this only for a general "quais são as promoções?" question. For a
    specific product or category use search_promotions instead.
    """
    async with _get_session_factory()() as session:
        rows = (
            await session.execute(
                select(models.Promotion, models.Product, models.Category.name)
                .join(models.Product, models.Product.product_id == models.Promotion.product_id)
                .outerjoin(
                    models.Category,
                    models.Category.category_id == models.Product.category_id,
                )
                .where(models.Promotion.is_active.is_(True))
                .order_by(models.Product.name)
            )
        ).all()

    return {
        "promotions": [
            _promotion_row(promo, product, category) for promo, product, category in rows
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
