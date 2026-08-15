import asyncio
import inspect
import logging
from typing import Sequence

from aioscraper.config import ErrorPolicy
from aioscraper.core import AIOScraper, run_scraper
from aioscraper.exceptions import CLIError

from ._args import parse_args
from ._entrypoint import resolve_entrypoint_factory

logger = logging.getLogger("aioscraper.cli")


def _apply_uvloop_policy():
    try:
        import uvloop  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dependency
        raise CLIError("uvloop is not installed. Install it to use the --uvloop flag.") from exc

    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("uvloop event loop policy enabled")
    except Exception as exc:  # pragma: no cover - platform specific failures
        raise CLIError("Failed to apply uvloop event loop policy") from exc


async def _run(entrypoint: str, concurrent_requests: int | None = None, pending_requests: int | None = None) -> int:
    logger.debug("Resolving entrypoint: %s", entrypoint)
    init = resolve_entrypoint_factory(entrypoint)
    scraper: AIOScraper = await init() if inspect.iscoroutinefunction(init) else init()

    if concurrent_requests is not None or pending_requests is not None:
        logger.info(
            "Overriding scheduler config: concurrent_requests=%s, pending_requests=%s",
            concurrent_requests or "default",
            pending_requests or "default",
        )
        if concurrent_requests:
            object.__setattr__(scraper.config.scheduler, "concurrent_requests", concurrent_requests)
        if pending_requests:
            object.__setattr__(scraper.config.scheduler, "pending_requests", pending_requests)

    logger.info("Starting scraper from entrypoint: %s", entrypoint)
    interrupted = await run_scraper(scraper)

    fail_on_error = scraper.config.execution.on_error is ErrorPolicy.FAIL
    counts = scraper.error_counts
    if counts:
        # Summary only: each error was already logged with its traceback where it happened.
        summary = ", ".join(f"{context}={count}" for context, count in sorted(counts.items()))
        logger.log(
            logging.ERROR if fail_on_error else logging.WARNING,
            "Finished with %d unhandled error(s): %s",
            sum(counts.values()),
            summary,
        )

    if interrupted:
        logger.info("Stopped by signal")
        return 130

    return 1 if counts and fail_on_error else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.logging:
            logging.basicConfig(level=args.log_level)
            logger.info("Logging enabled at level: %s", args.log_level)

        if args.uvloop:
            _apply_uvloop_policy()

        return asyncio.run(
            _run(
                args.entrypoint,
                concurrent_requests=args.concurrent_requests,
                pending_requests=args.pending_requests,
            ),
        )
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
