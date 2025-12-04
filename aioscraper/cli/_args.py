import argparse
from typing import Sequence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run aioscraper scrapers from the command line.")
    parser.add_argument("entrypoint", help="Path to the entrypoint file")
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
    return parser.parse_args(args=argv)
