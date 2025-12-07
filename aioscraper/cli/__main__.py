import asyncio
import inspect
import logging
from typing import Sequence

from ._args import parse_args
from ._entrypoint import resolve_entrypoint_factory
from ..exceptions import CLIError
from ..config import Config, load_config
from ..core import AIOScraper, run_scraper

logger = logging.getLogger("aioscraper.cli")


def _apply_uvloop_policy():
    try:
        import uvloop  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dependency
        raise CLIError("uvloop is not installed. Install it to use the --uvloop flag.") from exc

    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop event loop policy enabled")
    except Exception as exc:  # pragma: no cover - platform specific failures
        raise CLIError("Failed to apply uvloop event loop policy") from exc


async def _run(config: Config, entrypoint: str):
    init = resolve_entrypoint_factory(entrypoint)
    scraper: AIOScraper = await init() if inspect.iscoroutinefunction(init) else init()

    if scraper.config is None:
        scraper.config = config

    await run_scraper(scraper)


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    config = load_config(args.concurrent_requests, args.pending_requests)

    try:
        if args.logging:
            logging.basicConfig(level=args.log_level)

        if args.uvloop:
            _apply_uvloop_policy()

        asyncio.run(_run(config, args.entrypoint))
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")


if __name__ == "__main__":
    raise SystemExit(main())
