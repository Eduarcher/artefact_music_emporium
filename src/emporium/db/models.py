from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from emporium.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    price_brl: Mapped[float] = mapped_column(Float)
    name: Mapped[str] = mapped_column(String(255))
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.category_id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    specs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("ix_products_category_price", "category_id", "price_brl"),
    )


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.customer_id"))
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    total_brl: Mapped[float] = mapped_column(Float)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    estimated_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.order_id"))
    quantity: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.product_id"))


class Promotion(Base):
    __tablename__ = "promotions"

    promotion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.product_id"))
    discount_percent: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean)


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_version: Mapped[str] = mapped_column(String(50))
    section: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.customer_id"))
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.session_id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
