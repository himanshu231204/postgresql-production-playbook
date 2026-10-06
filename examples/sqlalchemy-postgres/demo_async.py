"""Async demo: N+1 vs selectinload, counted from the engine's statement events.

All writes are rolled back at the end, so the database is left unchanged.
Run: python demo_async.py
"""

import asyncio
from uuid import uuid4

from sqlalchemy import event, select, text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from models import Customer, Order
from repository import CustomerRepository
from session import make_async_engine, make_async_sessionmaker


def count_statements(engine: AsyncEngine) -> list[str]:
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _record(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:  # noqa: ANN001
        statements.append(statement)

    return statements


async def seed(session: AsyncSession, customers: int, orders_each: int) -> None:
    repo = CustomerRepository(session)
    for index in range(customers):
        customer = await repo.add(f"{uuid4().hex}@example.test", f"Customer {index}")
        for order_index in range(orders_each):
            await repo.add_order(customer.id, 1000 * (order_index + 1))


async def main() -> None:
    engine = make_async_engine()
    statements = count_statements(engine)
    sessionmaker = make_async_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            await seed(session, customers=5, orders_each=3)

            # 1. Lazy loading is blocked: a missing loader option fails loudly.
            customer = (await session.scalars(select(Customer).limit(1))).one()
            try:
                _ = customer.orders
            except InvalidRequestError as exc:
                print(f"lazy load blocked: {type(exc).__name__}")

            # 2. N+1 written by hand: 1 query for customers + 1 per customer.
            session.expunge_all()
            statements.clear()
            rows = (await session.scalars(select(Customer).limit(5))).all()
            for row in rows:
                await session.scalars(select(Order).where(Order.customer_id == row.id))
            print(f"N+1 style: {len(statements)} statements")

            # 3. selectinload: 2 statements regardless of customer count.
            session.expunge_all()
            statements.clear()
            loaded = await CustomerRepository(session).list_with_orders(limit=5)
            total_orders = sum(len(c.orders) for c in loaded)
            print(f"selectinload: {len(statements)} statements, {total_orders} orders")

            # 4. Roll back everything this demo wrote.
            await session.rollback()
            remaining = await session.scalar(text("SELECT count(*) FROM app.customers"))
            print(f"customers after rollback: {remaining}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
