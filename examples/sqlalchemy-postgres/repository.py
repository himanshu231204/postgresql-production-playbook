"""Repository over an AsyncSession. Flushes, never commits."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Customer, Order


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, email: str, name: str) -> Customer:
        customer = Customer(email=email, name=name)
        self._session.add(customer)
        await self._session.flush()  # assigns customer.id from the identity column
        return customer

    async def add_order(self, customer_id: int, total_cents: int) -> Order:
        order = Order(customer_id=customer_id, total_cents=total_cents)
        self._session.add(order)
        await self._session.flush()
        return order

    async def list_customers(self, limit: int) -> Sequence[Customer]:
        stmt = select(Customer).order_by(Customer.id).limit(limit)
        return (await self._session.scalars(stmt)).all()

    async def list_with_orders(self, limit: int) -> Sequence[Customer]:
        stmt = (
            select(Customer)
            .order_by(Customer.id)
            .limit(limit)
            .options(selectinload(Customer.orders))
        )
        return (await self._session.scalars(stmt)).all()
