import asyncio
import logging
from typing import Any, Sequence

from ._args import parse_args
from .exceptions import CLIError
from ..config import Config, load_config
from ._entrypoint import handle_lifespan, resolve_entrypoint
from ..scraper import AIOScraper


async def _run_scraper(config: Config, scraper: AIOScraper, lifespan: Any) -> None:
    async with handle_lifespan(lifespan, scraper):
        async with scraper:
            await scraper.start(config)


def _apply_uvloop_policy() -> None:
    try:
        import uvloop  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dependency
        raise CLIError("uvloop is not installed. Install it to use the --uvloop flag.") from exc

    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except Exception as exc:  # pragma: no cover - platform specific failures
        raise CLIError("Failed to apply uvloop event loop policy") from exc


def main(argv: Sequence[str] | None = None):
    args = parse_args(argv)
    config = load_config(args.concurrent_requests, args.pending_requests)

    try:
        if args.uvloop:
            _apply_uvloop_policy()

        asyncio.run(_run_scraper(config, *resolve_entrypoint(args.entrypoint)))
    except KeyboardInterrupt:
        logging.info("Interrupted, shutting down...")


if __name__ == "__main__":
    raise SystemExit(main())
