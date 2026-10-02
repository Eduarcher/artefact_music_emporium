from sqlalchemy import func, select

from emporium.db import models
from emporium.ingest.csv_ingest import ingest_csv

from .conftest import RAW_DATA_DIR


async def _snapshot(session_factory):
    """Capture a full snapshot of all operational tables for idempotency check."""
    snapshots = {}
    table_models = [
        (models.Category, "categories"),
        (models.Customer, "customers"),
        (models.Product, "products"),
        (models.Order, "orders"),
        (models.OrderItem, "order_items"),
        (models.Promotion, "promotions"),
    ]
    async with session_factory() as session:
        for model, name in table_models:
            rows = (
                await session.execute(
                    select(model).order_by(
                        *[col for col in model.__table__.primary_key.columns]
                    )
                )
            ).scalars().all()
            snapshots[name] = tuple(
                tuple(getattr(r, c.name) for c in model.__table__.columns) for r in rows
            )
    return snapshots


async def test_csv_ingestion_is_idempotent(engine, session_factory) -> None:
    """Running ingestion twice produces identical data."""
    await ingest_csv(engine, RAW_DATA_DIR)
    snap1 = await _snapshot(session_factory)
    await ingest_csv(engine, RAW_DATA_DIR)
    snap2 = await _snapshot(session_factory)
    assert snap1 == snap2


async def test_referential_integrity(engine, session_factory) -> None:
    """All foreign keys are valid after ingestion."""
    await ingest_csv(engine, RAW_DATA_DIR)
    await ingest_csv(engine, RAW_DATA_DIR)

    async with session_factory() as session:
        # Every order references an existing customer
        result = await session.execute(
            select(func.count()).select_from(models.Order).where(
                ~models.Order.customer_id.in_(select(models.Customer.customer_id))
            )
        )
        assert result.scalar() == 0

        # Every order_item references an existing order and product
        result = await session.execute(
            select(func.count()).select_from(models.OrderItem).where(
                ~models.OrderItem.order_id.in_(select(models.Order.order_id))
            )
        )
        assert result.scalar() == 0

        result = await session.execute(
            select(func.count()).select_from(models.OrderItem).where(
                ~models.OrderItem.product_id.in_(select(models.Product.product_id))
            )
        )
        assert result.scalar() == 0

        # Every product's category (if set) exists
        result = await session.execute(
            select(func.count()).select_from(models.Product).where(
                models.Product.category_id.is_not(None)
            ).where(
                ~models.Product.category_id.in_(select(models.Category.category_id))
            )
        )
        assert result.scalar() == 0

        # Every promotion references an existing product
        result = await session.execute(
            select(func.count()).select_from(models.Promotion).where(
                ~models.Promotion.product_id.in_(select(models.Product.product_id))
            )
        )
        assert result.scalar() == 0


async def test_known_records_materialized(engine, session_factory) -> None:
    """Specific known records are correctly materialized."""
    await ingest_csv(engine, RAW_DATA_DIR)
    await ingest_csv(engine, RAW_DATA_DIR)

    async with session_factory() as session:
        # Customer 1
        customer = (
            await session.execute(
                select(models.Customer).where(models.Customer.customer_id == 1)
            )
        ).scalar_one()
        assert customer.name == "Lucas Mendes da Silva"

        # Product 93 (Martin D-28)
        product = (
            await session.execute(
                select(models.Product).where(models.Product.product_id == 93)
            )
        ).scalar_one()
        assert product.name == "Martin D-28 Dreadnought Natural"
        assert product.price_brl == 11499.0

        # Order 15 has two items (82 and 106)
        await session.execute(
            select(models.Order).where(models.Order.order_id == 15)
        )
        items = (
            await session.execute(
                select(models.OrderItem).where(models.OrderItem.order_id == 15)
            )
        ).scalars().all()
        assert len(items) == 2
        product_ids = {i.product_id for i in items}
        assert product_ids == {82, 106}
