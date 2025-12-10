import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from aioscraper.core.scraper import AIOScraper
from aioscraper.exceptions import CLIError


def _resolve_file_path(module_ref: str) -> Path | None:
    path_ref = Path(module_ref)
    candidates = [path_ref]
    if path_ref.suffix != ".py":
        candidates.append(path_ref.with_suffix(".py"))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    return None


def _import_module(module_ref: str) -> ModuleType:
    module_path = _resolve_file_path(module_ref)

    if module_path is not None:
        package_parts: list[str] = []
        search_parent = module_path.parent
        while (search_parent / "__init__.py").exists():
            package_parts.append(search_parent.name)
            search_parent = search_parent.parent

        parts = list(reversed(package_parts))
        parts.append(module_path.stem)
        module_name = ".".join(parts)
        sys_path_entry = str(search_parent)
        if sys_path_entry not in sys.path:
            sys.path.insert(0, sys_path_entry)

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise CLIError(f"Unable to load module from '{module_ref}'")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    cwd_entry = str(Path.cwd())
    if cwd_entry not in sys.path:
        sys.path.insert(0, cwd_entry)

    try:
        return importlib.import_module(module_ref)
    except ModuleNotFoundError as exc:
        raise CLIError(f"Cannot find module '{module_ref}'") from exc


def _parse_entrypoint(target: str) -> tuple[str, str | None]:
    target_path = Path(target)
    if target_path.exists():
        return target, None

    module_ref, sep, attr = target.rpartition(":")
    if not sep:
        return target, None
    if not module_ref:
        raise CLIError("Entrypoint is missing module path before ':'")
    if not attr:
        raise CLIError("Entrypoint is missing callable name after ':'")

    return module_ref, attr


def _get_attr(module: ModuleType, name: str) -> Any:
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise CLIError(f"'{name}' not found in '{module.__name__}'") from exc


def resolve_entrypoint_factory(target: str) -> Callable[[], Any]:
    module_ref, attr = _parse_entrypoint(target)
    module = _import_module(module_ref)

    attr_name = attr or "scraper"
    scraper_obj = _get_attr(module, attr_name)

    if isinstance(scraper_obj, AIOScraper):
        return lambda: scraper_obj

    if inspect.iscoroutinefunction(scraper_obj):

        async def _resolve_async() -> AIOScraper:
            try:
                scraper = await scraper_obj()
            except Exception as exc:
                raise CLIError(f"Failed to await '{attr_name}'") from exc

            if isinstance(scraper, AIOScraper):
                return scraper

            raise CLIError(f"'{attr_name}' did not return an AIOScraper instance")

        return _resolve_async
    elif callable(scraper_obj):

        def _resolve_sync() -> AIOScraper:
            try:
                scraper = scraper_obj()
            except Exception as exc:
                raise CLIError(f"Failed to call '{attr_name}'") from exc

            if isinstance(scraper, AIOScraper):
                return scraper

            raise CLIError(f"'{attr_name}' did not return an AIOScraper instance")

        return _resolve_sync

    raise CLIError(f"'{attr_name}' is not an AIOScraper instance or factory")
