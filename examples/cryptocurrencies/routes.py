"""
FastAPI routes for cryptocurrency tracking API.

This module defines HTTP endpoints for retrieving cryptocurrency data,
triggering price refreshes, and checking task status.
"""

import asyncio
from typing import Annotated
from uuid import UUID

from database import CryptoCurrencyDatabase
from deps import get_cryptocurrency_database, get_queue
from fastapi import APIRouter, Depends
from models import Cryptocurrency, Task


async def get_cryptocurrency(
    cryptocurrency_id: int,
    database: Annotated[CryptoCurrencyDatabase, Depends(get_cryptocurrency_database)],
) -> Cryptocurrency:
    """Get cryptocurrency information by ID."""
    return await database.get(cryptocurrency_id)


async def refresh_cryptocurrency_price(
    cryptocurrency_id: int,
    database: Annotated[CryptoCurrencyDatabase, Depends(get_cryptocurrency_database)],
    queue: Annotated[asyncio.Queue[Task], Depends(get_queue)],
) -> Task:
    """Trigger a price refresh for a cryptocurrency."""
    # Create a new refresh task
    task = await database.refresh_price(cryptocurrency_id)
    # Add task to queue for processing by AIOScraper
    await queue.put(task)
    await database.commit()
    return task


async def get_task(
    task_id: UUID,
    database: Annotated[CryptoCurrencyDatabase, Depends(get_cryptocurrency_database)],
) -> Task:
    """
    Get task status by ID.

    Check the current status of a price refresh task.
    """
    return await database.get_task(task_id)


def get_api_router() -> APIRouter:
    """Create and configure the API router."""
    router = APIRouter(prefix="/api", tags=["cryptocurrencies"])

    router.add_api_route(
        "/cryptocurrencies/{cryptocurrency_id}",
        get_cryptocurrency,
        responses={400: {"description": "Cryptocurrency not found"}},
    )

    router.add_api_route(
        "/cryptocurrencies/{cryptocurrency_id}/refreshPrice",
        refresh_cryptocurrency_price,
        methods=["POST"],
        responses={400: {"description": "Cryptocurrency not found"}},
    )

    router.add_api_route(
        "/tasks/{task_id}",
        get_task,
        responses={400: {"description": "Task not found"}},
    )

    return router
