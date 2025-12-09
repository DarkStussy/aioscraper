"""
FastAPI dependency injection stubs.

This module defines dependency functions that are overridden at runtime
by the FastAPI lifespan context manager in app.py.
"""

import asyncio
from database import CryptoCurrencyDatabase
from models import Task


def get_queue() -> asyncio.Queue[Task]:
    raise NotImplementedError


def get_cryptocurrency_database() -> CryptoCurrencyDatabase:
    raise NotImplementedError
