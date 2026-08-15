import re
import textwrap
from pathlib import Path
from typing import Iterator, NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]

_MD_BLOCK = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)
_RST_DIRECTIVE = re.compile(r"^(\s*)\.\. code-block:: (?:python|py)\s*$")
_RST_OPTION = re.compile(r"^\s*:[\w-]+:")


class Snippet(NamedTuple):
    """A Python code block extracted from a documentation file.

    Attributes:
        path (Path): File the block was taken from.
        line (int): 1-based line number of the opening fence or directive.
        source (str): Dedented body of the block.
    """

    path: Path
    line: int
    source: str

    @property
    def id(self) -> str:
        return f"{self.path.relative_to(ROOT).as_posix()}:{self.line}"


def _markdown_snippets(path: Path) -> Iterator[Snippet]:
    text = path.read_text(encoding="utf-8")
    for match in _MD_BLOCK.finditer(text):
        yield Snippet(path, text.count("\n", 0, match.start()) + 1, match.group(1))


def _rst_snippets(path: Path) -> Iterator[Snippet]:
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        directive = _RST_DIRECTIVE.match(lines[index])
        if directive is None:
            index += 1
            continue

        indent = len(directive.group(1))
        start = index
        index += 1

        while index < len(lines) and (not lines[index].strip() or _RST_OPTION.match(lines[index])):
            index += 1

        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break

            body.append(line)
            index += 1

        while body and not body[-1].strip():
            body.pop()

        yield Snippet(path, start + 1, textwrap.dedent("\n".join(body)) + "\n")


def _collect_snippets() -> list[Snippet]:
    snippets = list(_markdown_snippets(ROOT / "README.md"))
    for path in sorted((ROOT / "docs").rglob("*.rst")):
        if "build" in path.parts:
            continue

        snippets.extend(_rst_snippets(path))

    return snippets


SNIPPETS = _collect_snippets()


def _syntax_error(snippet: Snippet) -> SyntaxError | None:
    """Compile a snippet, retrying inside a coroutine for bare ``await`` fragments.

    Args:
        snippet (Snippet): The extracted code block.

    Returns:
        SyntaxError | None: The original error, or ``None`` when the snippet compiles.
    """
    try:
        compile(snippet.source, snippet.id, "exec")
    except SyntaxError as exc:
        try:
            compile(f"async def _wrapper():\n{textwrap.indent(snippet.source, '    ')}", snippet.id, "exec")
        except SyntaxError:
            return exc

    return None


def test_snippets_are_collected():
    """Guard against the extractors silently matching nothing."""
    covered = {snippet.path for snippet in SNIPPETS}

    assert ROOT / "README.md" in covered
    assert ROOT / "docs" / "quickstart.rst" in covered


@pytest.mark.parametrize("snippet", SNIPPETS, ids=[snippet.id for snippet in SNIPPETS])
def test_documentation_snippet_compiles(snippet: Snippet):
    """Every documented Python block must be syntactically valid."""
    error = _syntax_error(snippet)
    if error is not None:
        pytest.fail(f"{type(error).__name__} on snippet line {error.lineno}: {error.msg}")
