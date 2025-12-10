import argparse
from typing import Callable, Sequence

from aioscraper.config.field_validators import RangeValidator


def _parse_int_factory(arg_name: str, validator: RangeValidator[int]) -> Callable[[str], int | None]:
    def _parse_int(value: str) -> int | None:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError("Value must be an integer") from None

        try:
            return validator(arg_name, int_value) or None
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    return _parse_int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    range_validator = RangeValidator(min_value=1)

    parser = argparse.ArgumentParser(description="Run aioscraper scrapers from the command line.")
    parser.add_argument("entrypoint", help="Path to the entrypoint module")
    parser.add_argument(
        "--concurrent-requests",
        type=_parse_int_factory("concurrent_requests", range_validator),
        default=None,
        help="Maximum number of concurrent requests (must be > 0)",
    )
    parser.add_argument(
        "--pending-requests",
        type=_parse_int_factory("pending_requests", range_validator),
        default=None,
        help="Number of pending requests to maintain (must be > 0)",
    )
    parser.add_argument(
        "--uvloop",
        action="store_true",
        help="Run scraper using uvloop event loop policy (requires uvloop to be installed)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--log", dest="logging", action="store_true", help="Enable logging")
    group.add_argument("--no-log", dest="logging", action="store_false", help="Disable logging")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )
    parser.set_defaults(logging=True)
    return parser.parse_args(args=argv)
