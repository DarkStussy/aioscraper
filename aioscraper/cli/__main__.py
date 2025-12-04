import asyncio
import logging
from typing import Callable, Sequence, AsyncContextManager

from ._args import parse_args
from ._config import build_config
from .exceptions import CLIError
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


def _apply_uvloop_policy() -> None:
    try:
        import uvloop  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dependency
        raise CLIError("uvloop is not installed. Install it to use the --uvloop flag.") from exc

    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except Exception as exc:  # pragma: no cover - platform specific failures
        raise CLIError("Failed to apply uvloop event loop policy.") from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = build_config(args.concurrent_requests, args.pending_requests)

    try:
        if args.uvloop:
            _apply_uvloop_policy()

        asyncio.run(_run(config, resolve_lifespan(args.entrypoint)))
    except CLIError as exc:
        logging.error(exc)
        return 1
    except KeyboardInterrupt:
        logging.info("Interrupted, shutting down...")
    except Exception:
        logging.exception("Scraper run failed")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
