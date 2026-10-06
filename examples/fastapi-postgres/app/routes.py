"""HTTP routes. Write handlers own the transaction: repository calls, then commit."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import SessionDep
from app.repositories import (
    CustomerNotFoundError,
    CustomerRepository,
    DuplicateEmailError,
    OrderRepository,
)
from app.schemas import (
    CustomerCreate,
    CustomerRead,
    CustomerWithOrders,
    OrderCreate,
    OrderRead,
)

logger = logging.getLogger(__name__)
router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=100)]
AfterId = Annotated[int, Query(ge=0)]


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Process is up. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: SessionDep, response: Response) -> dict[str, str]:
    """Database reachable. Bounded so a hung database fails the probe quickly."""
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
    except (SQLAlchemyError, OSError, TimeoutError):
        logger.exception("readiness check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
async def create_customer(body: CustomerCreate, session: SessionDep) -> CustomerRead:
    try:
        customer = await CustomerRepository(session).add(body.email, body.name)
    except DuplicateEmailError:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists") from None
    await session.commit()
    return CustomerRead.model_validate(customer)


@router.get("/customers", response_model=list[CustomerRead])
async def list_customers(
    session: SessionDep, limit: Limit = 50, after_id: AfterId = 0
) -> list[CustomerRead]:
    rows = await CustomerRepository(session).list_after(after_id, limit)
    return [CustomerRead.model_validate(row) for row in rows]


@router.get("/customers/with-orders", response_model=list[CustomerWithOrders])
async def list_customers_with_orders(
    session: SessionDep, limit: Limit = 20, after_id: AfterId = 0
) -> list[CustomerWithOrders]:
    rows = await CustomerRepository(session).list_with_orders(after_id, limit)
    return [CustomerWithOrders.model_validate(row) for row in rows]


@router.get("/customers/{customer_id}", response_model=CustomerRead)
async def get_customer(customer_id: int, session: SessionDep) -> CustomerRead:
    customer = await CustomerRepository(session).get(customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    return CustomerRead.model_validate(customer)


@router.post(
    "/customers/{customer_id}/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    customer_id: int, body: OrderCreate, session: SessionDep
) -> OrderRead:
    try:
        order = await OrderRepository(session).add(customer_id, body.total_cents)
    except CustomerNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from None
    await session.commit()
    return OrderRead.model_validate(order)


@router.get("/customers/{customer_id}/orders", response_model=list[OrderRead])
async def list_orders(
    customer_id: int, session: SessionDep, limit: Limit = 50
) -> list[OrderRead]:
    rows = await OrderRepository(session).list_for_customer(customer_id, limit)
    return [OrderRead.model_validate(row) for row in rows]
