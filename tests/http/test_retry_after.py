from aioscraper._helpers.http import parse_retry_after
from aioscraper.exceptions import HTTPException


def test_parse_retry_after_seconds():
    """Test parsing Retry-After header in seconds format."""
    exc = HTTPException(
        url="https://example.com",
        method="GET",
        headers={"Retry-After": "120"},
        status_code=429,
        message="Too Many Requests",
    )

    retry_after = parse_retry_after(exc)
    assert retry_after == 120.0


def test_parse_retry_after_case_insensitive():
    """Test that Retry-After parsing is case-insensitive."""

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        headers={"retry-after": "60"},  # lowercase
        status_code=503,
        message="Service Unavailable",
    )

    retry_after = parse_retry_after(exc)
    assert retry_after == 60.0
