"""ORM models (SQLAlchemy 2.x declarative). Tables come from sql/schema.sql."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(schema="app")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # lazy="raise": forgetting an explicit loader fails loudly instead of N+1.
    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer", lazy="raise", order_by="Order.id"
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app.customers.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    total_cents: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    customer: Mapped[Customer] = relationship(back_populates="orders", lazy="raise")
