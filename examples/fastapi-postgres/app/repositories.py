"""Repositories: all SQL lives here. They flush but never commit.

The caller (route handler / service) owns the transaction boundary.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Customer, Order

PG_UNIQUE_VIOLATION = "23505"
PG_FOREIGN_KEY_VIOLATION = "23503"


class DuplicateEmailError(Exception):
    """A customer with this email already exists."""


class CustomerNotFoundError(Exception):
    """The referenced customer does not exist."""


def _sqlstate(exc: IntegrityError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, customer_id: int) -> Customer | None:
        return await self._session.get(Customer, customer_id)

    async def list_after(self, after_id: int, limit: int) -> Sequence[Customer]:
        """Keyset pagination: stable and index-friendly, unlike OFFSET."""
        stmt = (
            select(Customer)
            .where(Customer.id > after_id)
            .order_by(Customer.id)
            .limit(limit)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_with_orders(self, after_id: int, limit: int) -> Sequence[Customer]:
        """Two queries total (customers, then orders IN (...)), not N+1."""
        stmt = (
            select(Customer)
            .where(Customer.id > after_id)
            .order_by(Customer.id)
            .limit(limit)
            .options(selectinload(Customer.orders))
        )
        return (await self._session.scalars(stmt)).all()

    async def add(self, email: str, name: str) -> Customer:
        customer = Customer(email=email, name=name)
        try:
            # SAVEPOINT: a constraint failure rolls back only this INSERT and
            # leaves the session usable.
            async with self._session.begin_nested():
                self._session.add(customer)
                await self._session.flush()
        except IntegrityError as exc:
            if _sqlstate(exc) == PG_UNIQUE_VIOLATION:
                raise DuplicateEmailError(email) from exc
            raise
        return customer


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_customer(self, customer_id: int, limit: int) -> Sequence[Order]:
        stmt = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.id)
            .limit(limit)
        )
        return (await self._session.scalars(stmt)).all()

    async def add(self, customer_id: int, total_cents: int) -> Order:
        order = Order(customer_id=customer_id, total_cents=total_cents)
        try:
            async with self._session.begin_nested():
                self._session.add(order)
                await self._session.flush()
        except IntegrityError as exc:
            if _sqlstate(exc) == PG_FOREIGN_KEY_VIOLATION:
                raise CustomerNotFoundError(customer_id) from exc
            raise
        return order
