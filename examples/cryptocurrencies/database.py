"""
In-memory database for cryptocurrency and task management.

This module provides a simple in-memory database implementation for demonstration purposes.
In production, this would be replaced with a real database (PostgreSQL, MongoDB, etc.).
"""

import asyncio
import logging
from uuid import UUID, uuid4
from models import Cryptocurrency, Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Exception raised for database-related errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CryptoCurrencyDatabase:
    """In-memory database for cryptocurrencies."""

    def __init__(self):
        self._cryptocurrencies = {
            1: Cryptocurrency(1, "BTC", 90000.0),
            2: Cryptocurrency(2, "ETH", 3000.0),
        }
        self._tasks: dict[UUID, Task] = {}

    async def get(self, cryptocurrency_id: int) -> Cryptocurrency:
        await asyncio.sleep(0.01)  # emulate IO
        if (cryptocurrency := self._cryptocurrencies.get(cryptocurrency_id)) is not None:
            return cryptocurrency

        raise DatabaseError("Cryptocurrency not found")

    async def exist(self, cryptocurrency_id: int) -> bool:
        await asyncio.sleep(0.01)  # emulate IO
        return cryptocurrency_id in self._cryptocurrencies

    async def get_task(self, task_id: UUID) -> Task:
        await asyncio.sleep(0.01)  # emulate IO
        if (task := self._tasks.get(task_id)) is not None:
            return task

        raise DatabaseError("Task not found")

    async def update_price(self, cryptocurrency_id: int, price: float):
        cryptocurrency = await self.get(cryptocurrency_id)
        cryptocurrency.price = price

    async def refresh_price(self, cryptocurrency_id: int) -> Task:
        cryptocurrency = await self.get(cryptocurrency_id)
        task = self._tasks[task.id] = self._create_task(cryptocurrency, TaskType.REFRESH_PRICE)
        return task

    async def update_task_status(self, task_id: UUID, status: TaskStatus):
        task = await self.get_task(task_id)
        task.status = status

    def _create_task(self, cryptocurrency: Cryptocurrency, task_type: TaskType) -> Task:
        return Task(uuid4(), cryptocurrency, type=task_type, status=TaskStatus.QUEUED)

    async def commit(self):
        """
        Commit transaction (placeholder for real database).

        In a real database implementation, this would commit the transaction.
        """
        ...

    async def close(self):
        """
        Close database connection.

        Simulates closing database connection and cleanup.
        """
        await asyncio.sleep(0.01)
        logger.info("Database closed")
