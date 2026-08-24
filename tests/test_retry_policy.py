import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import pytest

from aioscraper.config import BackoffStrategy, RequestRetryConfig
from aioscraper.core.retry import RetryPolicy
from aioscraper.exceptions import (
    ConnectionFailed,
    DNSError,
    HTTPException,
    ProxyError,
    TLSError,
    TransportError,
    TransportTimeout,
)
from aioscraper.types import Request

URL = "https://example.com"


def _policy(**overrides) -> RetryPolicy:
    settings = {
        "enabled": True,
        "attempts": 3,
        "base_delay": 0.1,
        "max_delay": 30.0,
        "backoff": BackoffStrategy.CONSTANT,
        "statuses": (500, 502, 429, 503),
        "exceptions": (),
        **overrides,
    }
    return RetryPolicy(RequestRetryConfig(**settings))


def _http_error(status: int = 502, headers: dict[str, str] | None = None, method: str = "GET") -> HTTPException:
    return HTTPException(
        url="https://example.com",
        method=method,
        status_code=status,
        headers=headers or {},
        message="boom",
    )


def test_status_triggers_a_retry():
    assert _policy().next_delay(Request(url="https://example.com"), _http_error(), 0) == 0.1


def test_unmatched_failure_is_not_retried():
    assert _policy().next_delay(Request(url="https://example.com"), RuntimeError("boom"), 0) is None


def test_exception_type_triggers_a_retry():
    policy = _policy(statuses=(), exceptions=(asyncio.TimeoutError,))

    assert policy.next_delay(Request(url="https://example.com"), asyncio.TimeoutError(), 0) == 0.1


def test_disabled_policy_never_retries():
    assert _policy(enabled=False).next_delay(Request(url="https://example.com"), _http_error(), 0) is None


def test_exhausted_attempts_stop_the_retry():
    policy = _policy(attempts=2)
    request = Request(url="https://example.com")

    assert policy.next_delay(request, _http_error(), 1) == 0.1
    assert policy.next_delay(request, _http_error(), 2) is None


def test_non_idempotent_method_is_not_retried():
    request = Request(url="https://example.com", method="POST")

    assert _policy().next_delay(request, _http_error(method="POST"), 0) is None


def test_method_check_is_case_insensitive():
    policy = _policy(methods=("get",))

    assert policy.next_delay(Request(url="https://example.com", method="Get"), _http_error(), 0) == 0.1


def test_retryable_overrides_the_method_check():
    request = Request(url="https://example.com", method="POST", retryable=True)

    assert _policy().next_delay(request, _http_error(method="POST"), 0) == 0.1


def test_retryable_false_blocks_a_retryable_method():
    request = Request(url="https://example.com", retryable=False)

    assert _policy().next_delay(request, _http_error(), 0) is None


def test_the_default_policy_retries_a_failing_status():
    assert RetryPolicy(RequestRetryConfig()).next_delay(Request(url=URL), _http_error(503), 0) is not None


@pytest.mark.parametrize(
    ("exc", "retried"),
    [
        (TransportTimeout(URL, "GET", "timed out"), True),
        (ConnectionFailed(URL, "GET", "connection refused"), True),
        (DNSError(URL, "GET", "unknown host"), True),
        (ProxyError(URL, "GET", "proxy refused"), True),
        (TLSError(URL, "GET", "bad certificate"), False),
        (TransportError(URL, "GET", "unclassified"), False),
    ],
)
def test_the_default_exceptions_cover_transient_transport_failures(exc: Exception, retried: bool):
    """Backend-neutral by construction: every backend raises these same classes."""
    policy = RetryPolicy(RequestRetryConfig(enabled=True, attempts=3, base_delay=0.1, backoff=BackoffStrategy.CONSTANT))

    assert (policy.next_delay(Request(url=URL), exc, 0) is not None) is retried


def test_should_retry_decides_an_unmatched_failure():
    policy = _policy(should_retry=lambda request, exc, retries: isinstance(exc, RuntimeError))

    assert policy.next_delay(Request(url="https://example.com"), RuntimeError("boom"), 0) == 0.1


def test_should_retry_can_veto_a_matching_status():
    policy = _policy(should_retry=lambda request, exc, retries: False)

    assert policy.next_delay(Request(url="https://example.com"), _http_error(), 0) is None


def test_should_retry_returning_none_falls_back_to_the_status_match():
    policy = _policy(should_retry=lambda request, exc, retries: None)
    request = Request(url="https://example.com")

    assert policy.next_delay(request, _http_error(), 0) == 0.1
    assert policy.next_delay(request, RuntimeError("boom"), 0) is None


def test_should_retry_cannot_widen_the_method_check():
    """The idempotency guard outranks the hook: it protects against duplicating an effect."""
    policy = _policy(should_retry=lambda request, exc, retries: True)
    request = Request(url="https://example.com", method="POST")

    assert policy.next_delay(request, _http_error(method="POST"), 0) is None


def test_should_retry_receives_the_retry_count():
    seen: list[int] = []

    def should_retry(request: Request, exc: Exception, retries: int) -> bool:
        seen.append(retries)
        return True

    policy = _policy(should_retry=should_retry)
    request = Request(url="https://example.com")

    policy.next_delay(request, _http_error(), 0)
    policy.next_delay(request, _http_error(), 2)

    assert seen == [0, 2]


def test_linear_backoff_grows_with_the_retry_count():
    policy = _policy(backoff=BackoffStrategy.LINEAR)
    request = Request(url="https://example.com")

    assert policy.next_delay(request, _http_error(), 0) == 0.1
    assert policy.next_delay(request, _http_error(), 1) == 0.2


def test_exponential_backoff_is_capped_by_max_delay():
    policy = _policy(backoff=BackoffStrategy.EXPONENTIAL, base_delay=0.1, max_delay=0.5)
    request = Request(url="https://example.com")

    assert policy.next_delay(request, _http_error(), 0) == 0.2  # 0.1 * (2**1)
    assert policy.next_delay(request, _http_error(), 1) == 0.4  # 0.1 * (2**2)
    assert policy.next_delay(request, _http_error(), 2) == 0.5  # capped


def test_exponential_jitter_backoff():
    policy = _policy(backoff=BackoffStrategy.EXPONENTIAL_JITTER, base_delay=0.1, max_delay=1.0)

    with patch("random.uniform", return_value=0.05):
        # delay = 0.1 * (2**1) = 0.2; (delay / 2) + jitter
        assert policy.next_delay(Request(url="https://example.com"), _http_error(), 0) == 0.15


def test_retry_after_seconds_overrides_the_backoff():
    error = _http_error(status=429, headers={"Retry-After": "5"})

    assert _policy().next_delay(Request(url="https://example.com"), error, 0) == 5.0


def test_retry_after_http_date_overrides_the_backoff():
    retry_at = datetime.now(UTC) + timedelta(seconds=10)
    error = _http_error(status=503, headers={"Retry-After": format_datetime(retry_at, usegmt=True)})

    delay = _policy().next_delay(Request(url="https://example.com"), error, 0)

    assert delay is not None
    assert 9.0 <= delay <= 11.0


def test_retry_after_is_case_insensitive():
    error = _http_error(status=429, headers={"retry-after": "3"})

    assert _policy().next_delay(Request(url="https://example.com"), error, 0) == 3.0


def test_retry_after_is_capped():
    error = _http_error(status=503, headers={"Retry-After": "100000"})

    assert _policy().next_delay(Request(url="https://example.com"), error, 0) == 600.0


@pytest.mark.parametrize("retries", [0, 4])
def test_delay_never_depends_on_request_state(retries: int):
    """The count comes from the attempt, so the request object carries nothing."""
    policy = _policy(attempts=10, backoff=BackoffStrategy.LINEAR)
    request = Request(url="https://example.com")

    assert policy.next_delay(request, _http_error(), retries) == pytest.approx(0.1 * (retries + 1))
    assert request.state == {}
    assert request.delay is None
