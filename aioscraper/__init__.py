__title__ = "aioscraper"

__author__ = "darkstussy"

__copyright__ = f"Copyright (c) 2025 {__author__}"

from ._helpers import compiled
from .core import AIOScraper, RunResult, run_scraper
from .types import File, Pipeline, Request, Response, ScheduleRequest

__all__ = (
    "AIOScraper",
    "File",
    "Pipeline",
    "Request",
    "Response",
    "RunResult",
    "ScheduleRequest",
    "compiled",
    "run_scraper",
)
