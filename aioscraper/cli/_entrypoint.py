import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


from .exceptions import CLIError
from ..scraper.core import AIOScraper


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


def _coerce_scraper(obj: Any, attr_name: str) -> AIOScraper:
    if isinstance(obj, AIOScraper):
        return obj

    if callable(obj):
        try:
            produced = obj()
        except Exception as exc:
            raise CLIError(f"Failed to call '{attr_name}'") from exc

        if isinstance(produced, AIOScraper):
            return produced

        raise CLIError(f"'{attr_name}' did not return an AIOScraper instance")

    raise CLIError(f"'{attr_name}' is not an AIOScraper instance or factory")


def resolve_entrypoint(target: str) -> AIOScraper:
    module_ref, attr = _parse_entrypoint(target)
    module = _import_module(module_ref)

    attr_name = attr or "scraper"
    scraper_obj = _get_attr(module, attr_name)
    return _coerce_scraper(scraper_obj, attr_name)
