import csv
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from emporium.db import models

_TABLE_FILENAMES = {
    "categories": "categories",
    "customers": "customers",
    "order_items": "order_items",
    "orders": "orders",
    "products": "products",
    "promotions": "promotions",
}

# Truncate children before parents, then insert parents before children.
_TRUNCATE_ORDER = [
    "order_items",
    "promotions",
    "orders",
    "products",
    "customers",
    "categories",
]

_INSERT_ORDER = [
    "categories",
    "customers",
    "products",
    "orders",
    "promotions",
    "order_items",
]


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: str) -> float:
    value = value.strip()
    if not value:
        return 0.0
    return float(value.replace(",", "."))


def _parse_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


def _parse_specs(value: str) -> dict | None:
    value = value.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "s", "t"}


_ROW_PARSERS = {
    "categories": lambda r: {
        "category_id": _parse_int(r["category_id"]),
        "name": r["name"],
        "description": r.get("description") or None,
    },
    "customers": lambda r: {
        "customer_id": _parse_int(r["customer_id"]),
        "name": r["name"],
        "phone": r.get("phone") or None,
        "email": r.get("email") or None,
        "city": r.get("city") or None,
    },
    "products": lambda r: {
        "product_id": _parse_int(r["product_id"]),
        "price_brl": _parse_float(r["price_brl"]),
        "name": r["name"],
        "category_id": _parse_int(r.get("category_id") or ""),
        "description": r.get("description") or None,
        "stock_quantity": _parse_int(r.get("stock_quantity") or "0") or 0,
        "status": r.get("status") or "",
        "specs": _parse_specs(r.get("specs") or ""),
        "created_at": _parse_date(r.get("created_at") or ""),
    },
    "orders": lambda r: {
        "order_id": _parse_int(r["order_id"]),
        "customer_id": _parse_int(r["customer_id"]),
        "order_date": _parse_date(r.get("order_date") or ""),
        "status": r.get("status") or "",
        "total_brl": _parse_float(r["total_brl"]),
        "payment_method": r.get("payment_method") or None,
        "tracking_code": r.get("tracking_code") or None,
        "estimated_delivery": _parse_date(r.get("estimated_delivery") or ""),
        "notes": r.get("notes") or None,
    },
    "order_items": lambda r: {
        "order_id": _parse_int(r["order_id"]),
        "quantity": _parse_int(r.get("quantity") or "1") or 1,
        "product_id": _parse_int(r["product_id"]),
    },
    "promotions": lambda r: {
        "promotion_id": _parse_int(r["promotion_id"]),
        "product_id": _parse_int(r["product_id"]),
        "discount_percent": _parse_float(r["discount_percent"]),
        "description": r.get("description") or None,
        "is_active": _parse_bool(r.get("is_active") or "0"),
    },
}

_TABLES = {
    "categories": models.Category,
    "customers": models.Customer,
    "products": models.Product,
    "orders": models.Order,
    "order_items": models.OrderItem,
    "promotions": models.Promotion,
}


def _find_csv_files(raw_data_dir: Path) -> dict[str, Path]:
    files = {p.name: p for p in raw_data_dir.glob("*.csv")}
    result: dict[str, Path] = {}
    for table, keyword in _TABLE_FILENAMES.items():
        for name, path in files.items():
            if keyword in name.lower():
                result[table] = path
                break
        else:
            raise FileNotFoundError(f"CSV for table '{table}' not found in {raw_data_dir}")
    return result


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


async def ingest_csv(engine: AsyncEngine, raw_data_dir: Path) -> dict[str, int]:
    files = _find_csv_files(raw_data_dir)
    counts: dict[str, int] = {}

    async with engine.begin() as conn:
        for table in _TRUNCATE_ORDER:
            await conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))

        for table in _INSERT_ORDER:
            if table not in files:
                continue
            rows = _read_rows(files[table])
            parsed = [_ROW_PARSERS[table](row) for row in rows]
            model = _TABLES[table]
            if parsed:
                await conn.execute(pg_insert(model.__table__).values(parsed))
            counts[table] = len(parsed)

    return counts
