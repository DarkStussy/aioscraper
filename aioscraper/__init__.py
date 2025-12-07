__title__ = "aioscraper"

__author__ = "darkstussy"

__copyright__ = f"Copyright (c) 2025 {__author__}"

from .core import AIOScraper, run_scraper
from .types import Request, Response, SendRequest, Pipeline, File

__all__ = ("AIOScraper", "run_scraper", "Request", "Response", "SendRequest", "Pipeline", "File")
