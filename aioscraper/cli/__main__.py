import asyncio
import logging
from typing import Callable, Sequence, AsyncContextManager

from ._args import parse_args
from ._config import build_config
from ..config import Config
from ._entrypoint import handle_lifespan, resolve_lifespan
from ..scraper import AIOScraper


async def _run(config: Config, lifespan: Callable[[AIOScraper], AsyncContextManager[None]]) -> None:
    executor = AIOScraper(config=config)
    try:
        async with handle_lifespan(lifespan, executor):
            await executor.start()
    finally:
        await executor.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = build_config(args.concurrent_requests, args.pending_requests)

    try:
        asyncio.run(_run(config, resolve_lifespan(args.entrypoint)))
    except KeyboardInterrupt:
        logging.info("Interrupted, shutting down...")
    except Exception:
        logging.exception("Scraper run failed")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
