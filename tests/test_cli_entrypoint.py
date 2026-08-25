from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest

from aioscraper.cli.__main__ import _run
from aioscraper.cli._entrypoint import resolve_entrypoint_factory
from aioscraper.core import AIOScraper, run_scraper
from aioscraper.exceptions import CLIError, ConfigValidationError


def _write_module(tmp_path: Path, code: str) -> Path:
    path = tmp_path / "mod.py"
    path.write_text(dedent(code))
    return path


def test_resolve_instance(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        scraper = AIOScraper()
        """,
    )

    scraper = resolve_entrypoint_factory(str(path))()
    assert isinstance(scraper, AIOScraper)


def test_resolve_factory_with_attr(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        def make():
            return AIOScraper()
        """,
    )

    scraper = resolve_entrypoint_factory(f"{path}:make")()
    assert isinstance(scraper, AIOScraper)


def test_resolve_factory_default_attr(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        def scraper():
            return AIOScraper()
        """,
    )

    scraper = resolve_entrypoint_factory(str(path))()
    assert isinstance(scraper, AIOScraper)


async def test_resolve_async_factory(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        async def build():
            return AIOScraper()
        """,
    )

    init = resolve_entrypoint_factory(f"{path}:build")
    scraper = await init()
    assert isinstance(scraper, AIOScraper)


def test_factory_returns_wrong_type(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        def build():
            return "not-a-scraper"
        """,
    )

    with pytest.raises(CLIError):
        resolve_entrypoint_factory(f"{path}:build")()


def test_attr_not_found(tmp_path: Path):
    path = _write_module(tmp_path, "x = 1")

    with pytest.raises(CLIError):
        resolve_entrypoint_factory(f"{path}:missing")()


def test_relative_module_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        scraper = AIOScraper()
        """,
    )
    # simulate running from parent dir
    monkeypatch.chdir(tmp_path.parent)
    rel_path = Path(tmp_path.name) / path.name

    scraper = resolve_entrypoint_factory(str(rel_path))()
    assert isinstance(scraper, AIOScraper)


def test_resolve_entrypoint_missing_module_raises():
    with pytest.raises(CLIError):
        resolve_entrypoint_factory("this.module.does.not.exist")()


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent_requests", [0, -1])
async def test_scheduler_override_is_validated(tmp_path: Path, concurrent_requests: int):
    """A CLI override goes through the field validators, not straight into the frozen config."""
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        scraper = AIOScraper()
        """,
    )

    with pytest.raises(ConfigValidationError, match="concurrent_requests"):
        await _run(str(path), concurrent_requests=concurrent_requests)


@pytest.mark.asyncio
async def test_scheduler_override_applies(tmp_path: Path):
    path = _write_module(
        tmp_path,
        """
        from aioscraper import AIOScraper
        scraper = AIOScraper()
        """,
    )

    captured: dict[str, int] = {}

    async def capture(scraper: AIOScraper):
        captured["concurrent_requests"] = scraper.config.scheduler.concurrent_requests
        captured["pending_requests"] = scraper.config.scheduler.pending_requests
        return await run_scraper(scraper)

    with patch("aioscraper.cli.__main__.run_scraper", capture):
        await _run(str(path), concurrent_requests=7)

    assert captured == {"concurrent_requests": 7, "pending_requests": 1}
