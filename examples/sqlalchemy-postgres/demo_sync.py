"""Sync demo (psycopg 3): same model and queries through a blocking Session.

Run: python demo_sync.py
"""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from models import Customer
from session import make_sync_engine, make_sync_sessionmaker


def main() -> None:
    engine = make_sync_engine()
    sessionmaker = make_sync_sessionmaker(engine)
    try:
        # begin() commits on success and rolls back on exception.
        with sessionmaker.begin() as session:
            stmt = (
                select(Customer)
                .order_by(Customer.id)
                .limit(5)
                .options(selectinload(Customer.orders))
            )
            customers = session.scalars(stmt).all()
            count = session.scalar(select(func.count()).select_from(Customer))
            print(f"loaded {len(customers)} customers; table has {count}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
