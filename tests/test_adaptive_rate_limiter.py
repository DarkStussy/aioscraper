import asyncio
from unittest.mock import AsyncMock

import pytest

from aioscraper._helpers.http import parse_retry_after
from aioscraper.config.models import AdaptiveRateLimitConfig, RateLimitConfig, RequestRetryConfig
from aioscraper.core.rate_limiter import (
    AdaptiveMetrics,
    AdaptiveStrategy,
    RateLimiterManager,
    RequestOutcome,
)
from aioscraper.exceptions import HTTPException
from aioscraper.types.session import Request, PRequest


class TestAdaptiveMetrics:
    """Tests for AdaptiveMetrics EWMA tracking."""

    def test_ewma_calculation_first_request(self):
        """Test that first request initializes EWMA directly."""
        metrics = AdaptiveMetrics(ewma_alpha=0.3)
        metrics.record_success(latency=1.0)

        assert metrics.ewma_latency == 1.0
        assert metrics.total_requests == 1
        assert metrics.success_count == 1
        assert metrics.failure_count == 0

    def test_ewma_calculation_smoothing(self):
        """Test that EWMA smoothing works correctly."""
        metrics = AdaptiveMetrics(ewma_alpha=0.3)

        # First request
        metrics.record_success(latency=1.0)
        assert metrics.ewma_latency == 1.0

        # Second request: EWMA = 0.3 * 2.0 + 0.7 * 1.0 = 1.3
        metrics.record_success(latency=2.0)
        assert abs(metrics.ewma_latency - 1.3) < 0.001

        # Third request: EWMA = 0.3 * 0.5 + 0.7 * 1.3 = 1.06
        metrics.record_success(latency=0.5)
        assert abs(metrics.ewma_latency - 1.06) < 0.001

    def test_success_count_tracking(self):
        """Test that consecutive success count is tracked correctly."""
        metrics = AdaptiveMetrics()

        metrics.record_success(1.0)
        assert metrics.success_count == 1
        assert metrics.failure_count == 0

        metrics.record_success(1.0)
        assert metrics.success_count == 2
        assert metrics.failure_count == 0

        metrics.record_failure(1.0)
        assert metrics.success_count == 0
        assert metrics.failure_count == 1

    def test_failure_count_tracking(self):
        """Test that consecutive failure count is tracked correctly."""
        metrics = AdaptiveMetrics()

        metrics.record_failure(1.0)
        assert metrics.failure_count == 1
        assert metrics.success_count == 0

        metrics.record_failure(1.0)
        assert metrics.failure_count == 2
        assert metrics.success_count == 0

        metrics.record_success(1.0)
        assert metrics.failure_count == 0
        assert metrics.success_count == 1


class TestAdaptiveStrategy:
    """Tests for AdaptiveStrategy AIMD logic."""

    def test_multiplicative_increase_on_failure(self):
        """Test that interval increases multiplicatively on failure."""
        strategy = AdaptiveStrategy(
            min_interval=0.001,
            max_interval=5.0,
            increase_factor=2.0,
            decrease_step=0.01,
            success_threshold=5,
        )

        outcome = RequestOutcome(group_key="test", latency=1.0, status_code=503)

        # First failure: 0.1 * 2.0 = 0.2
        new_interval = strategy.calculate_interval("test", current_interval=0.1, outcome=outcome)
        assert new_interval == 0.2

        # Second failure: 0.2 * 2.0 = 0.4
        new_interval = strategy.calculate_interval("test", current_interval=0.2, outcome=outcome)
        assert new_interval == 0.4

    def test_additive_decrease_on_success(self):
        """Test that interval decreases additively after success threshold."""
        strategy = AdaptiveStrategy(
            min_interval=0.001,
            max_interval=5.0,
            increase_factor=2.0,
            decrease_step=0.01,
            success_threshold=3,
        )

        outcome = RequestOutcome(group_key="test", latency=0.5)

        current_interval = 1.0

        # First success: not enough, interval unchanged
        new_interval = strategy.calculate_interval("test", current_interval, outcome)
        assert new_interval == 1.0

        # Second success: not enough, interval unchanged
        new_interval = strategy.calculate_interval("test", current_interval, outcome)
        assert new_interval == 1.0

        # Third success: threshold reached, decrease by 0.01
        new_interval = strategy.calculate_interval("test", current_interval, outcome)
        assert new_interval == 0.99

        # Fourth success: continue decreasing
        new_interval = strategy.calculate_interval("test", 0.99, outcome)
        assert new_interval == 0.98

    def test_respects_min_max_bounds(self):
        """Test that interval respects min/max bounds."""
        strategy = AdaptiveStrategy(
            min_interval=0.01,
            max_interval=1.0,
            increase_factor=10.0,
            decrease_step=0.5,
        )

        # Test max bound
        failure_outcome = RequestOutcome(group_key="test", latency=1.0, status_code=429)

        new_interval = strategy.calculate_interval("test", current_interval=0.5, outcome=failure_outcome)
        assert new_interval <= 1.0  # Should not exceed max

        # Build up success count
        success_outcome = RequestOutcome(group_key="test", latency=0.1)
        for _ in range(5):
            strategy.calculate_interval("test", 0.5, success_outcome)

        # Test min bound
        new_interval = strategy.calculate_interval("test", current_interval=0.02, outcome=success_outcome)
        assert new_interval >= 0.01  # Should not go below min

    def test_retry_after_override(self):
        """Test that Retry-After header overrides AIMD logic."""
        strategy = AdaptiveStrategy(
            min_interval=0.001,
            max_interval=5.0,
            respect_retry_after=True,
        )

        outcome = RequestOutcome(group_key="test", latency=1.0, retry_after=3.5, status_code=429)

        new_interval = strategy.calculate_interval("test", current_interval=0.1, outcome=outcome)
        assert new_interval == 3.5  # Should use Retry-After value

    def test_retry_after_respects_max_bound(self):
        """Test that Retry-After is capped at max_interval."""
        strategy = AdaptiveStrategy(
            min_interval=0.001,
            max_interval=2.0,
            respect_retry_after=True,
        )

        outcome = RequestOutcome(
            group_key="test",
            latency=1.0,
            retry_after=10.0,  # Higher than max
            status_code=503,
        )

        new_interval = strategy.calculate_interval("test", current_interval=0.1, outcome=outcome)
        assert new_interval == 2.0  # Should be capped at max_interval

    def test_per_group_independence(self):
        """Test that metrics are tracked independently per group."""
        strategy = AdaptiveStrategy(success_threshold=2)

        outcome_a = RequestOutcome(group_key="group-a", latency=0.5)

        # Build up success count for group-a
        strategy.calculate_interval("group-a", 1.0, outcome_a)
        strategy.calculate_interval("group-a", 1.0, outcome_a)

        metrics_a = strategy.get_or_create_metrics("group-a")
        metrics_b = strategy.get_or_create_metrics("group-b")

        assert metrics_a.success_count == 2
        assert metrics_b.success_count == 0

    def test_reset_metrics(self):
        """Test that metrics can be reset for a group."""
        strategy = AdaptiveStrategy()

        outcome = RequestOutcome(group_key="test", latency=0.5)
        strategy.calculate_interval("test", 1.0, outcome)

        metrics = strategy.get_or_create_metrics("test")
        assert metrics.total_requests == 1

        strategy.reset_metrics("test")
        metrics = strategy.get_or_create_metrics("test")
        assert metrics.total_requests == 0  # Should be fresh metrics


class TestAdaptiveRateLimiterIntegration:
    """Integration tests for adaptive rate limiting."""

    @pytest.mark.asyncio
    async def test_adaptive_slows_down_on_failures(self):
        """Test that adaptive strategy slows down when encountering failures."""
        from time import monotonic

        call_intervals = []
        last_call_time = None

        async def mock_schedule(pr: PRequest):
            nonlocal last_call_time
            start = monotonic()
            current_time = asyncio.get_event_loop().time()
            if last_call_time is not None:
                call_intervals.append(current_time - last_call_time)
            last_call_time = current_time

            # Simulate server error on first two requests
            if len(call_intervals) < 2:
                exc = HTTPException(
                    url=pr.request.url,
                    method="GET",
                    headers={},
                    status_code=503,
                    message="Service Unavailable",
                )
                # Simulate RequestManager feedback
                latency = monotonic() - start
                outcome = RequestOutcome(
                    group_key="example.com",
                    latency=latency,
                    retry_after=None,
                    status_code=503,
                    exception_type=HTTPException,
                )
                manager.on_request_outcome(outcome)
                raise exc

        config = RateLimitConfig(
            enabled=True,
            default_interval=0.05,
            cleanup_timeout=2.0,
            adaptive=AdaptiveRateLimitConfig(
                enabled=True,
                min_interval=0.01,
                max_interval=1.0,
                increase_factor=2.0,
            ),
        )

        manager = RateLimiterManager(config, retry_config=RequestRetryConfig(), schedule=mock_schedule)

        for i in range(4):
            pr = PRequest(priority=i, request=Request(url=f"https://example.com/{i}"))
            await manager(pr)

        await asyncio.sleep(1.0)

        # Verify that intervals increased after failures
        # After 1st failure, interval should double: 0.05 -> 0.1
        # After 2nd failure, interval should double again: 0.1 -> 0.2
        assert len(call_intervals) >= 2
        if len(call_intervals) >= 3:
            # Second interval should be larger than first (after first failure)
            assert call_intervals[1] > call_intervals[0]

        await manager.close()

    @pytest.mark.asyncio
    async def test_adaptive_respects_retry_after(self):
        """Test that adaptive strategy respects Retry-After headers."""
        from time import monotonic

        call_times = []

        async def mock_schedule(pr: PRequest):
            start = monotonic()
            call_times.append(asyncio.get_event_loop().time())

            if len(call_times) == 1:
                exc = HTTPException(
                    url=pr.request.url,
                    method="GET",
                    headers={"Retry-After": "0.2"},
                    status_code=429,
                    message="Too Many Requests",
                )
                # Simulate RequestManager feedback
                latency = monotonic() - start
                outcome = RequestOutcome(
                    group_key="example.com",
                    latency=latency,
                    retry_after=parse_retry_after(exc),
                    status_code=429,
                    exception_type=HTTPException,
                )
                manager.on_request_outcome(outcome)
                raise exc

        config = RateLimitConfig(
            enabled=True,
            default_interval=0.01,
            adaptive=AdaptiveRateLimitConfig(
                enabled=True,
                respect_retry_after=True,
            ),
        )

        manager = RateLimiterManager(config, retry_config=RequestRetryConfig(), schedule=mock_schedule)

        pr1 = PRequest(priority=1, request=Request(url="https://example.com/1"))
        pr2 = PRequest(priority=2, request=Request(url="https://example.com/2"))

        await manager(pr1)
        await manager(pr2)

        await asyncio.sleep(0.5)

        # Second request should wait approximately the Retry-After duration
        if len(call_times) >= 2:
            interval = call_times[1] - call_times[0]
            assert interval >= 0.2 - 0.05  # Allow some tolerance

        await manager.close()

    @pytest.mark.asyncio
    async def test_adaptive_with_retry_config_triggers(self):
        """Test that adaptive strategy inherits triggers from retry config."""
        retry_config = RequestRetryConfig(
            enabled=True,
            statuses=(500, 503),
            exceptions=(asyncio.TimeoutError,),
        )

        config = RateLimitConfig(
            enabled=True,
            default_interval=0.01,
            adaptive=AdaptiveRateLimitConfig(
                enabled=True,
                inherit_retry_triggers=True,
            ),
        )

        manager = RateLimiterManager(config, schedule=AsyncMock(), retry_config=retry_config)

        # Verify that triggers were inherited
        assert manager.adaptive_strategy is not None
        assert 500 in manager.adaptive_strategy.trigger_statuses
        assert 503 in manager.adaptive_strategy.trigger_statuses
        assert asyncio.TimeoutError in manager.adaptive_strategy.trigger_exceptions

        await manager.close()

    @pytest.mark.asyncio
    async def test_non_adaptive_mode_unchanged(self):
        """Test that non-adaptive mode works as before."""
        call_times = []

        async def mock_schedule(pr: PRequest):
            call_times.append(asyncio.get_event_loop().time())

        config = RateLimitConfig(
            enabled=True,
            default_interval=0.05,
            adaptive=AdaptiveRateLimitConfig(enabled=False),  # Disabled
        )

        manager = RateLimiterManager(config, retry_config=RequestRetryConfig(), schedule=mock_schedule)

        for i in range(3):
            pr = PRequest(priority=i, request=Request(url=f"https://example.com/{i}"))
            await manager(pr)

        await asyncio.sleep(0.3)

        # Intervals should be constant (non-adaptive)
        intervals = [call_times[i] - call_times[i - 1] for i in range(1, len(call_times))]
        if len(intervals) >= 2:
            # All intervals should be approximately the same
            assert all(abs(interval - 0.05) < 0.02 for interval in intervals)

        await manager.close()
