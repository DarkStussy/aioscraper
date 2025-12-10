import asyncio
import logging

import pytest

from aioscraper.config.models import (
    AdaptiveRateLimitConfig,
    BackoffStrategy,
    Config,
    ExecutionConfig,
    HttpBackend,
    PipelineConfig,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
    SessionConfig,
)
from aioscraper.exceptions import ConfigValidationError


class TestSessionConfig:
    def test_creates_with_defaults(self):
        config = SessionConfig()

        assert config.timeout == 60.0
        assert config.ssl is True
        assert config.proxy is None
        assert config.http_backend is None

    def test_validates_timeout_min(self):
        with pytest.raises(ConfigValidationError, match=r"timeout.*minimum is 0.001"):
            SessionConfig(timeout=0.0)

    def test_validates_timeout_max_boundary(self):
        config = SessionConfig(timeout=0.001)
        assert config.timeout == 0.001

    def test_accepts_valid_timeout(self):
        config = SessionConfig(timeout=30.0)
        assert config.timeout == 30.0

    def test_accepts_string_timeout(self):
        config = SessionConfig(timeout="45.5")  # type: ignore[reportArgumentType]
        assert config.timeout == 45.5
        assert isinstance(config.timeout, float)

    def test_accepts_bool_ssl(self):
        config = SessionConfig(ssl=False)
        assert config.ssl is False

    def test_accepts_string_ssl(self):
        config = SessionConfig(ssl="false")  # type: ignore[reportArgumentType]
        assert config.ssl is False

    def test_accepts_proxy_string(self):
        config = SessionConfig(proxy="http://proxy:8080")
        assert config.proxy == "http://proxy:8080"

    def test_accepts_proxy_dict(self):
        proxy: dict[str, str | None] = {"http": "http://p1:8080", "https": "http://p2:8080"}
        config = SessionConfig(proxy=proxy)
        assert config.proxy == {"http://": "http://p1:8080", "https://": "http://p2:8080"}

    def test_accepts_http_backend_enum(self):
        config = SessionConfig(http_backend=HttpBackend.AIOHTTP)
        assert config.http_backend == HttpBackend.AIOHTTP

    def test_accepts_http_backend_string(self):
        config = SessionConfig(http_backend="httpx")  # type: ignore[reportArgumentType]
        assert config.http_backend == HttpBackend.HTTPX


class TestRequestRetryConfig:
    def test_creates_with_defaults(self):
        config = RequestRetryConfig()

        assert config.enabled is False
        assert config.attempts == 3
        assert config.backoff == BackoffStrategy.EXPONENTIAL_JITTER
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.statuses == (500, 502, 503, 504, 522, 524, 408, 429)
        assert config.exceptions == (asyncio.TimeoutError,)

    def test_validates_attempts_min(self):
        with pytest.raises(ConfigValidationError, match=r"attempts.*minimum is 1"):
            RequestRetryConfig(attempts=0)

    def test_validates_base_delay_min(self):
        with pytest.raises(ConfigValidationError, match=r"base_delay.*minimum is 0.001"):
            RequestRetryConfig(base_delay=0.0)

    def test_validates_max_delay_min(self):
        with pytest.raises(ConfigValidationError, match=r"max_delay.*minimum is 0.001"):
            RequestRetryConfig(max_delay=0.0)

    def test_accepts_valid_attempts(self):
        config = RequestRetryConfig(attempts=5)
        assert config.attempts == 5

    def test_accepts_string_attempts(self):
        config = RequestRetryConfig(attempts="10")  # type: ignore[reportArgumentType]
        assert config.attempts == 10

    def test_delay_factory_constant(self):
        config = RequestRetryConfig(backoff=BackoffStrategy.CONSTANT, base_delay=1.0)
        factory = config.delay_factory

        assert factory(0) == 1.0
        assert factory(1) == 1.0
        assert factory(5) == 1.0

    def test_delay_factory_linear(self):
        config = RequestRetryConfig(backoff=BackoffStrategy.LINEAR, base_delay=1.0)
        factory = config.delay_factory

        assert factory(0) == 0.0
        assert factory(1) == 1.0
        assert factory(2) == 2.0
        assert factory(5) == 5.0

    def test_delay_factory_exponential(self):
        config = RequestRetryConfig(backoff=BackoffStrategy.EXPONENTIAL, base_delay=1.0, max_delay=10.0)
        factory = config.delay_factory

        assert factory(0) == 1.0
        assert factory(1) == 2.0
        assert factory(2) == 4.0
        assert factory(3) == 8.0
        assert factory(10) == 10.0  # capped at max_delay

    def test_delay_factory_exponential_jitter(self):
        config = RequestRetryConfig(backoff=BackoffStrategy.EXPONENTIAL_JITTER, base_delay=1.0, max_delay=10.0)
        factory = config.delay_factory

        # Test that jitter produces values in expected range
        for attempt in range(5):
            delay = factory(attempt)
            expected_base = min(10.0, 1.0 * (2**attempt))
            assert expected_base / 2 <= delay <= expected_base


class TestAdaptiveRateLimitConfig:
    def test_creates_with_defaults(self):
        config = AdaptiveRateLimitConfig()

        assert config.min_interval == 0.001
        assert config.max_interval == 5.0
        assert config.increase_factor == 2.0
        assert config.decrease_step == 0.01
        assert config.success_threshold == 5
        assert config.ewma_alpha == 0.3
        assert config.respect_retry_after is True
        assert config.inherit_retry_triggers is True

    def test_validates_min_interval(self):
        with pytest.raises(ConfigValidationError, match=r"min_interval.*minimum is 0.001"):
            AdaptiveRateLimitConfig(min_interval=0.0)

    def test_validates_max_interval(self):
        with pytest.raises(ConfigValidationError, match=r"max_interval.*minimum is 0.001"):
            AdaptiveRateLimitConfig(max_interval=0.0)

    def test_validates_increase_factor(self):
        with pytest.raises(ConfigValidationError, match=r"increase_factor.*minimum is 1.0"):
            AdaptiveRateLimitConfig(increase_factor=0.5)

    def test_validates_decrease_step(self):
        with pytest.raises(ConfigValidationError, match=r"decrease_step.*minimum is 0.001"):
            AdaptiveRateLimitConfig(decrease_step=0.0)

    def test_validates_success_threshold(self):
        with pytest.raises(ConfigValidationError, match=r"success_threshold.*minimum is 1"):
            AdaptiveRateLimitConfig(success_threshold=0)

    def test_validates_ewma_alpha_range(self):
        with pytest.raises(ConfigValidationError, match=r"ewma_alpha.*minimum is 0.0"):
            AdaptiveRateLimitConfig(ewma_alpha=-0.1)

        with pytest.raises(ConfigValidationError, match=r"ewma_alpha.*maximum is 1.0"):
            AdaptiveRateLimitConfig(ewma_alpha=1.5)

    def test_accepts_valid_values(self):
        config = AdaptiveRateLimitConfig(
            min_interval=0.1,
            max_interval=10.0,
            increase_factor=1.5,
            decrease_step=0.05,
            success_threshold=3,
            ewma_alpha=0.5,
        )

        assert config.min_interval == 0.1
        assert config.max_interval == 10.0
        assert config.increase_factor == 1.5
        assert config.decrease_step == 0.05
        assert config.success_threshold == 3
        assert config.ewma_alpha == 0.5


class TestRateLimitConfig:
    def test_creates_with_defaults(self):
        config = RateLimitConfig()

        assert config.enabled is False
        assert config.group_by is None
        assert config.default_interval == 0.0
        assert config.cleanup_timeout == 60.0
        assert config.adaptive is None

    def test_validates_default_interval(self):
        with pytest.raises(ConfigValidationError, match=r"default_interval.*minimum is 0.0"):
            RateLimitConfig(default_interval=-1.0)

    def test_validates_cleanup_timeout(self):
        with pytest.raises(ConfigValidationError, match=r"cleanup_timeout.*minimum is 0.1"):
            RateLimitConfig(cleanup_timeout=0.01)

    def test_accepts_adaptive_config(self):
        adaptive = AdaptiveRateLimitConfig(min_interval=0.1)
        config = RateLimitConfig(adaptive=adaptive)

        assert config.adaptive == adaptive


class TestSchedulerConfig:
    def test_creates_with_defaults(self):
        config = SchedulerConfig()

        assert config.concurrent_requests == 64
        assert config.pending_requests == 1
        assert config.close_timeout == 0.1
        assert config.ready_queue_max_size == 0

    def test_validates_concurrent_requests_min(self):
        with pytest.raises(ConfigValidationError, match=r"concurrent_requests.*minimum is 1"):
            SchedulerConfig(concurrent_requests=0)

    def test_validates_pending_requests_min(self):
        with pytest.raises(ConfigValidationError, match=r"pending_requests.*minimum is 1"):
            SchedulerConfig(pending_requests=0)

    def test_validates_close_timeout_min(self):
        with pytest.raises(ConfigValidationError, match=r"close_timeout.*minimum is 0.01"):
            SchedulerConfig(close_timeout=0.001)

    def test_validates_ready_queue_max_size_min(self):
        with pytest.raises(ConfigValidationError, match=r"ready_queue_max_size.*minimum is 0"):
            SchedulerConfig(ready_queue_max_size=-1)

    def test_accepts_valid_values(self):
        config = SchedulerConfig(
            concurrent_requests=10,
            pending_requests=5,
            close_timeout=1.0,
            ready_queue_max_size=100,
        )

        assert config.concurrent_requests == 10
        assert config.pending_requests == 5
        assert config.close_timeout == 1.0
        assert config.ready_queue_max_size == 100

    def test_accepts_string_values(self):
        config = SchedulerConfig(concurrent_requests="20", pending_requests="10", close_timeout="2.5")  # type: ignore[reportArgumentType]

        assert config.concurrent_requests == 20
        assert config.pending_requests == 10
        assert config.close_timeout == 2.5


class TestExecutionConfig:
    def test_creates_with_defaults(self):
        config = ExecutionConfig()

        assert config.timeout is None
        assert config.shutdown_timeout == 0.1
        assert config.shutdown_check_interval == 0.1
        assert config.log_level == logging.ERROR

    def test_validates_timeout_min(self):
        with pytest.raises(ConfigValidationError, match=r"timeout.*minimum is 0.01"):
            ExecutionConfig(timeout=0.001)

    def test_validates_shutdown_timeout_min(self):
        with pytest.raises(ConfigValidationError, match=r"shutdown_timeout.*minimum is 0.001"):
            ExecutionConfig(shutdown_timeout=0.0)

    def test_validates_shutdown_check_interval_min(self):
        with pytest.raises(ConfigValidationError, match=r"shutdown_check_interval.*minimum is 0.01"):
            ExecutionConfig(shutdown_check_interval=0.001)

    def test_accepts_none_timeout(self):
        config = ExecutionConfig(timeout=None)
        assert config.timeout is None

    def test_accepts_valid_timeout(self):
        config = ExecutionConfig(timeout=30.0)
        assert config.timeout == 30.0

    def test_accepts_string_timeout(self):
        config = ExecutionConfig(timeout="45.5")  # type: ignore[reportArgumentType]
        assert config.timeout == 45.5


class TestPipelineConfig:
    def test_creates_with_defaults(self):
        config = PipelineConfig()
        assert config.strict is True

    def test_accepts_string_bool(self):
        config = PipelineConfig(strict="false")  # type: ignore[reportArgumentType]
        assert config.strict is False


class TestConfig:
    def test_creates_with_defaults(self):
        config = Config()

        assert isinstance(config.session, SessionConfig)
        assert isinstance(config.scheduler, SchedulerConfig)
        assert isinstance(config.execution, ExecutionConfig)
        assert isinstance(config.pipeline, PipelineConfig)

    def test_creates_with_custom_session(self):
        session = SessionConfig(timeout=30.0)
        config = Config(session=session)

        assert config.session.timeout == 30.0

    def test_creates_with_custom_scheduler(self):
        scheduler = SchedulerConfig(concurrent_requests=10)
        config = Config(scheduler=scheduler)

        assert config.scheduler.concurrent_requests == 10

    def test_creates_with_custom_execution(self):
        execution = ExecutionConfig(timeout=60.0)
        config = Config(execution=execution)

        assert config.execution.timeout == 60.0

    def test_creates_with_custom_pipeline(self):
        pipeline = PipelineConfig(strict=False)
        config = Config(pipeline=pipeline)

        assert config.pipeline.strict is False

    def test_validates_nested_configs(self):
        with pytest.raises(ConfigValidationError):
            Config(session=SessionConfig(timeout=0.0))

        with pytest.raises(ConfigValidationError):
            Config(scheduler=SchedulerConfig(concurrent_requests=0))

        with pytest.raises(ConfigValidationError):
            Config(execution=ExecutionConfig(timeout=0.001))
