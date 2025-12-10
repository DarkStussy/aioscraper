"""
FastAPI application for cryptocurrency price tracking.

This application integrates AIOScraper with FastAPI to provide a REST API
for tracking cryptocurrency prices using CoinMarketCap API.

The application demonstrates how to:
- Integrate AIOScraper with FastAPI's lifespan events
- Use dependency injection for shared resources (database, queue)
- Create asynchronous background tasks with AIOScraper
- Handle custom exceptions with FastAPI
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from database import CryptoCurrencyDatabase, DatabaseError
from deps import get_cryptocurrency_database, get_queue
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from routes import get_api_router
from scraper import CryptocurrencyPriceScraper

from aioscraper import AIOScraper
from aioscraper.config import env, load_config


def db_error_handler(_, exc: DatabaseError):
    """Handle database errors and return appropriate HTTP response."""
    return JSONResponse(status_code=400, content={"message": exc.message})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown.

    Handles:
    - Initialization of database and task queue
    - Setting up dependency injection overrides
    - Starting AIOScraper background worker
    - Graceful shutdown of scraper and database
    """
    # Initialize shared resources
    queue = asyncio.Queue()
    database = CryptoCurrencyDatabase()

    # Override dependency stubs with actual instances
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_cryptocurrency_database] = lambda: database

    # Initialize the cryptocurrency price scraper
    cryptocurrency_price_scraper = CryptocurrencyPriceScraper(env.parse("CMC_API_KEY"))
    scraper_runner = AIOScraper(cryptocurrency_price_scraper, config=load_config())

    # Inject dependencies into scraper callbacks
    scraper_runner.add_dependencies(queue=queue, database=database)

    # Start scraper in the background
    scraper_runner.start()

    try:
        yield
    finally:
        # Graceful shutdown
        await scraper_runner.shutdown()
        await database.close()


def create_app():
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(lifespan=lifespan)
    app.include_router(get_api_router())
    app.add_exception_handler(DatabaseError, db_error_handler)  # type: ignore[reportArgumentType]
    return app
