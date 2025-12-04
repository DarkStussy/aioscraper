from pathlib import Path
import sys
from textwrap import dedent

import pytest

from aioscraper import AIOScraper
from aioscraper.cli._entrypoint import CLIError, handle_lifespan, resolve_entrypoint

TEST_SCRAPER_CODE = """
from aioscraper import AIOScraper

scraper = AIOScraper()
"""

TEST_SCRAPER_LIFESPAN_CODE = """
from contextlib import asynccontextmanager
from aioscraper import AIOScraper

scraper = AIOScraper()

@asynccontextmanager
async def lifespan(scraper):
    yield "ok"
"""

TEST_ONLY_LIFESPAN_CODE = """
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(scraper):
    yield "ok"
"""


def _write_module(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(dedent(body))
    return path


def test_resolve_entrypoint_uses_scraper_and_lifespan(tmp_path: Path):
    module_path = _write_module(tmp_path, "myscraper", TEST_SCRAPER_LIFESPAN_CODE)

    scraper, lifespan = resolve_entrypoint(str(module_path))

    try:
        assert scraper is sys.modules[module_path.stem].scraper
        assert lifespan is sys.modules[module_path.stem].lifespan
    finally:
        sys.modules.pop(module_path.stem, None)


@pytest.mark.asyncio
async def test_handle_lifespan_wraps_context_manager(tmp_path: Path):
    module_path = _write_module(tmp_path, "with_lifespan", TEST_SCRAPER_LIFESPAN_CODE)

    scraper, lifespan = resolve_entrypoint(str(module_path))
    try:
        async with handle_lifespan(lifespan, scraper) as value:
            assert value == "ok"
    finally:
        sys.modules.pop(module_path.stem, None)


def test_resolve_entrypoint_with_py_path_and_attr(tmp_path: Path):
    module_path = _write_module(tmp_path, "myscraper_attr", TEST_SCRAPER_CODE)

    scraper, _ = resolve_entrypoint(f"{module_path}:scraper")

    try:
        assert isinstance(scraper, AIOScraper)
    finally:
        sys.modules.pop(module_path.stem, None)


def test_resolve_entrypoint_lifespan_attr_creates_scraper(tmp_path: Path):
    module_path = _write_module(tmp_path, "only_lifespan", TEST_ONLY_LIFESPAN_CODE)

    scraper, lifespan = resolve_entrypoint(f"{module_path}:lifespan")

    try:
        assert isinstance(scraper, AIOScraper)
        assert lifespan is sys.modules[module_path.stem].lifespan
    finally:
        sys.modules.pop(module_path.stem, None)


def test_resolve_entrypoint_rejects_non_scraper(tmp_path: Path):
    module_path = _write_module(tmp_path, "bad_attr", "not_scraper = object()")

    with pytest.raises(CLIError):
        resolve_entrypoint(f"{module_path}:not_scraper")

    sys.modules.pop(module_path.stem, None)


def test_handle_lifespan_requires_async_context_manager():
    scraper = AIOScraper()

    def not_a_contextmanager(_):
        return "nope"

    with pytest.raises(CLIError):
        handle_lifespan(not_a_contextmanager, scraper)


def test_resolve_entrypoint_missing_module_raises():
    with pytest.raises(CLIError):
        resolve_entrypoint("this.module.does.not.exist")


def test_resolve_entrypoint_relative_path(tmp_path: Path, monkeypatch):
    module_path = _write_module(tmp_path, "rel_scraper", TEST_SCRAPER_CODE)
    monkeypatch.chdir(tmp_path)

    scraper, _ = resolve_entrypoint(module_path.name)
    try:
        assert scraper is sys.modules["rel_scraper"].scraper
    finally:
        sys.modules.pop("rel_scraper", None)


def test_resolve_entrypoint_relative_path_with_attr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = _write_module(tmp_path, "rel_with_attr", TEST_SCRAPER_CODE)
    monkeypatch.chdir(tmp_path)

    scraper, _ = resolve_entrypoint(f"{module_path.name}:scraper")
    try:
        assert scraper is sys.modules["rel_with_attr"].scraper
    finally:
        sys.modules.pop("rel_with_attr", None)
