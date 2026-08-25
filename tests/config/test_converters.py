import ssl

import pytest

from aioscraper.config.converters import parse_exception, parse_ssl
from aioscraper.exceptions import TransportTimeout


def test_parse_exception_imports_a_dotted_path():
    assert parse_exception("aioscraper.exceptions.TransportTimeout") is TransportTimeout


@pytest.mark.parametrize(
    ("path", "match", "cause"),
    [
        ("TransportTimeout", "fully qualified", None),
        ("aioscraper.nonexistent.Boom", "Cannot import", ModuleNotFoundError),
        ("aioscraper.exceptions.NoSuchError", "Cannot import", AttributeError),
        ("aioscraper.config.Config", "not an exception type", None),
    ],
)
def test_parse_exception_rejects_a_bad_path(path: str, match: str, cause: type[Exception] | None):
    """Every rejection is a ValueError, whatever the import machinery raised underneath."""
    with pytest.raises(ValueError, match=match) as exc_info:
        parse_exception(path)

    if cause is None:
        assert exc_info.value.__cause__ is None
    else:
        assert isinstance(exc_info.value.__cause__, cause)


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("TRUE", True), ("false", False)])
def test_parse_ssl_reads_a_boolean_word(value: str, expected: bool):
    assert parse_ssl(value) is expected


def test_parse_ssl_loads_a_ca_bundle():
    certifi = pytest.importorskip("certifi")

    context = parse_ssl(certifi.where())

    assert isinstance(context, ssl.SSLContext)
    assert context.get_ca_certs()


@pytest.mark.parametrize("value", ["/no/such/bundle.pem", "yes", "1"])
def test_parse_ssl_rejects_a_path_it_cannot_load(value: str):
    """A word that is not true/false is a path, so a truthy-looking one fails as a missing file."""
    with pytest.raises(ValueError, match="Cannot load a CA bundle") as exc_info:
        parse_ssl(value)

    assert isinstance(exc_info.value.__cause__, OSError)
