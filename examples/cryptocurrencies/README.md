# Cryptocurrency Price Tracker

Real-world example of integrating **aioscraper** with **FastAPI** to build a cryptocurrency price tracking REST API.

## Overview

Demonstrates how to:
- Fetch cryptocurrency prices from CoinMarketCap API using aioscraper
- Integrate aioscraper with FastAPI's lifespan events
- Use dependency injection for shared resources (database, queue)
- Process background tasks with asyncio queues

## Architecture

- **app.py** - FastAPI application
- **routes.py** - API endpoints
- **scraper.py** - aioscraper implementation
- **database.py** - In-memory database (replace with real DB in production)
- **models.py** - Data models
- **deps.py** - Dependency injection stubs

## API Endpoints

- **GET /api/cryptocurrencies/{id}** - Get cryptocurrency with current price
- **POST /api/cryptocurrencies/{id}/refreshPrice** - Trigger price refresh
- **GET /api/tasks/{uuid}** - Check task status

## Prerequisites

- Python 3.11+
- CoinMarketCap API key from [coinmarketcap.com/api](https://coinmarketcap.com/api/)

## Installation

```bash
pip install aioscraper fastapi[standard]
```

## Running

Set your CoinMarketCap API key:
```bash
export CMC_API_KEY="your-api-key-here"
```

Start the application:
```bash
fastapi dev --entrypoint=app:create_app
```

Application starts on `http://localhost:8000`

**API docs**: http://localhost:8000/docs

## Usage

**Get cryptocurrency:**
```bash
curl http://localhost:8000/api/cryptocurrencies/1
```

**Trigger price refresh:**
```bash
curl -X POST http://localhost:8000/api/cryptocurrencies/1/refreshPrice
```

**Check task status:**
```bash
curl http://localhost:8000/api/tasks/{task_id}
```

## Configuration

aioscraper configuration: [Environment Variables](https://aioscraper.readthedocs.io/en/latest/cli.html#environment-variables)

## Notes

For production use:
- Replace in-memory database with PostgreSQL/MongoDB
- Use message broker (RabbitMQ, AWS SQS, Redis) instead of `asyncio.Queue` for reliable task distribution
