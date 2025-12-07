import argparse
from typing import Sequence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run aioscraper scrapers from the command line.")
    parser.add_argument("entrypoint", help="Path to the entrypoint module")
    parser.add_argument(
        "--concurrent-requests",
        type=int,
        default=None,
        help="Maximum number of concurrent requests",
    )
    parser.add_argument(
        "--pending-requests",
        type=int,
        default=None,
        help="Number of pending requests to maintain",
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
