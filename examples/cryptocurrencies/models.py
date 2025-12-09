"""
Data models for cryptocurrency tracking system.

Contains dataclass models for cryptocurrencies and tasks, as well as enum types
for task statuses and types.
"""

from dataclasses import dataclass
from enum import StrEnum, auto
from uuid import UUID


@dataclass(slots=True)
class Cryptocurrency:
    """
    Cryptocurrency model.

    Attributes:
        id (int): Unique cryptocurrency identifier
        name (str): Cryptocurrency symbol (e.g., BTC, ETH)
        price (float): Current cryptocurrency price in USDC
    """

    id: int
    name: str
    price: float


class TaskType(StrEnum):
    """
    Task types for processing.

    Attributes:
        REFRESH_PRICE: Task to refresh cryptocurrency price
    """

    REFRESH_PRICE = auto()


class TaskStatus(StrEnum):
    """
    Task execution statuses.

    Attributes:
        QUEUED: Task added to queue, waiting for processing
        IN_PROGRESS: Task is being processed
        SUCCESS: Task completed successfully
    """

    QUEUED = auto()
    IN_PROGRESS = auto()
    SUCCESS = auto()


@dataclass(slots=True)
class Task:
    """
    Task model for processing.

    Attributes:
        id (UUID): Unique task identifier (UUID)
        cryptocurrency (Cryptocurrency): Cryptocurrency for which the task is executed
        type (TaskType): Task type (e.g., price refresh)
        status (TaskStatus): Current task execution status
    """

    id: UUID
    cryptocurrency: Cryptocurrency
    type: TaskType
    status: TaskStatus
