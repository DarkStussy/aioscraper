import asyncio
from typing import Hashable
from unittest.mock import AsyncMock

import pytest

from aioscraper.config import RateLimitConfig, RequestRetryConfig
from aioscraper.core.rate_limiter import RateLimitManager, RequestGroup, default_group_by_factory
from aioscraper.types.session import PRequest, Request


@pytest.fixture
def mock_schedule():
    return AsyncMock()


@pytest.fixture
def captured_groups():
    return {}


@pytest.fixture
def on_group_finished_factory(captured_groups):
    def factory():
        def on_finished(key: Hashable, group: RequestGroup):
            captured_groups[key] = group

        return on_finished

    return factory


class TestRequestGroup:
    @pytest.mark.asyncio
    async def test_request_group_processes_requests_with_interval(self, mock_schedule, on_group_finished_factory):
        """Test that RequestGroup processes requests with the specified interval."""
        interval = 0.05
        call_times = []
        on_finished = on_group_finished_factory()

        async def schedule_with_timing(pr: PRequest):
            call_times.append(asyncio.get_event_loop().time())
            await mock_schedule(pr)

        group = RequestGroup(
            key="test-group",
            interval=interval,
            cleanup_timeout=1.0,
            schedule=schedule_with_timing,
            on_finished=on_finished,
        )
        group.start_listening()

        pr1 = PRequest(priority=1, request=Request(url="https://example.com/1"))
        pr2 = PRequest(priority=2, request=Request(url="https://example.com/2"))
        pr3 = PRequest(priority=3, request=Request(url="https://example.com/3"))

        await group.put(pr1)
        await group.put(pr2)
        await group.put(pr3)

        # Wait for all requests to be processed
        await asyncio.sleep(interval * 3 + 0.2)

        assert mock_schedule.call_count == 3

        # Verify intervals between calls
        for i in range(1, len(call_times)):
            elapsed = call_times[i] - call_times[i - 1]
            assert elapsed >= interval - 0.01, f"Expected interval >= {interval}, got {elapsed}"

        await group.close()

    @pytest.mark.asyncio
    async def test_request_group_cleanup_on_idle_timeout(self, mock_schedule, captured_groups):
        """Test that RequestGroup cleans up after idle timeout."""
        cleanup_timeout = 0.1
        calls = []

        def on_finished(key: Hashable, group: RequestGroup):
            calls.append(("finished", key))
            captured_groups[key] = group

        group = RequestGroup(
            key="idle-group",
            interval=0.01,
            cleanup_timeout=cleanup_timeout,
            schedule=mock_schedule,
            on_finished=on_finished,
        )
        group.start_listening()

        pr = PRequest(priority=1, request=Request(url="https://example.com/idle"))
        await group.put(pr)

        await asyncio.sleep(0.05)
        assert mock_schedule.call_count == 1

        await asyncio.sleep(cleanup_timeout + 0.1)

        # on_finished should be called
        assert ("finished", "idle-group") in calls
        assert "idle-group" in captured_groups

        await group.close()

    @pytest.mark.asyncio
    async def test_request_group_close_cancels_worker(self, mock_schedule, on_group_finished_factory):
        """Test that closing RequestGroup cancels its worker task."""
        on_finished = on_group_finished_factory()

        group = RequestGroup(
            key="cancel-group",
            interval=0.01,
            cleanup_timeout=1.0,
            schedule=mock_schedule,
            on_finished=on_finished,
        )
        group.start_listening()

        assert group.worker_alive

        await group.close()

        assert not group.worker_alive

    @pytest.mark.asyncio
    async def test_request_group_handles_schedule_error(self, captured_groups):
        """Test that RequestGroup handles errors from schedule callback."""
        errors_logged = []

        async def failing_schedule(pr: PRequest):
            error = RuntimeError(f"Failed to schedule {pr.request.url}")
            errors_logged.append(error)
            raise error

        def on_finished(key: Hashable, group: RequestGroup):
            captured_groups[key] = group

        group = RequestGroup(
            key="error-group",
            interval=0.01,
            cleanup_timeout=0.2,
            schedule=failing_schedule,
            on_finished=on_finished,
        )
        group.start_listening()

        pr = PRequest(priority=1, request=Request(url="https://example.com/fail"))
        await group.put(pr)

        await asyncio.sleep(0.05)

        # Error should be logged but group should continue
        assert len(errors_logged) == 1
        assert group.worker_alive

        await group.close()

    @pytest.mark.asyncio
    async def test_request_group_active_property(self, mock_schedule, on_group_finished_factory):
        """Test the active property of RequestGroup."""
        on_finished = on_group_finished_factory()

        group = RequestGroup(
            key="active-group",
            interval=0.01,
            cleanup_timeout=1.0,
            schedule=mock_schedule,
            on_finished=on_finished,
        )
        group.start_listening()

        assert not group.active

        pr = PRequest(priority=1, request=Request(url="https://example.com/active"))
        await group.put(pr)

        assert group.active

        await asyncio.sleep(0.05)

        assert not group.active

        await group.close()

    @pytest.mark.asyncio
    async def test_request_group_minimum_cleanup_timeout(self, mock_schedule, on_group_finished_factory):
        """Test that cleanup_timeout is at least 2x the interval."""
        interval = 0.1
        cleanup_timeout = 0.05  # Less than 2x interval

        group = RequestGroup(
            key="min-timeout-group",
            interval=interval,
            cleanup_timeout=cleanup_timeout,
            schedule=mock_schedule,
            on_finished=on_group_finished_factory(),
        )
        group.start_listening()

        # cleanup_timeout should be adjusted to at least 2x interval
        assert group._cleanup_timeout >= interval * 2

        await group.close()


class TestRateLimitManager:
    @pytest.mark.asyncio
    async def test_rate_limiter_groups_by_hostname(self, mock_schedule):
        """Test that rate limiter groups requests by hostname when enabled."""
        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, default_interval=0.05),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            pr1 = PRequest(priority=1, request=Request(url="https://example.com/page1"))
            pr2 = PRequest(priority=2, request=Request(url="https://example.com/page2"))
            pr3 = PRequest(priority=3, request=Request(url="https://other.com/page1"))

            await manager(pr1)
            await manager(pr2)
            await manager(pr3)

            assert len(manager._groups) == 2
            assert "example.com" in manager._groups
            assert "other.com" in manager._groups

            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_rate_limiter_disabled_applies_simple_delay(self, mock_schedule):
        """Test that disabled rate limiter still applies default_interval."""
        call_times = []
        default_interval = 0.05

        async def schedule_with_timing(pr: PRequest):
            call_times.append(asyncio.get_event_loop().time())
            await mock_schedule(pr)

        async with RateLimitManager(
            config=RateLimitConfig(enabled=False, default_interval=default_interval),
            retry_config=RequestRetryConfig(),
            schedule=schedule_with_timing,
        ) as manager:
            pr1 = PRequest(priority=1, request=Request(url="https://example.com/1"))
            pr2 = PRequest(priority=2, request=Request(url="https://example.com/2"))

            await manager(pr1)
            await manager(pr2)

            assert len(manager._groups) == 0

            # Verify calls and timing
            assert len(call_times) == 2
            elapsed = call_times[1] - call_times[0]
            assert elapsed >= default_interval - 0.01

    @pytest.mark.asyncio
    async def test_rate_limiter_custom_group_by(self, mock_schedule):
        """Test rate limiter with custom group_by function."""

        def custom_group_by(request: Request) -> tuple[Hashable, float]:
            # Group by path and use different intervals
            if "fast" in request.url:
                return ("fast", 0.01)

            return ("slow", 0.05)

        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, group_by=custom_group_by),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            pr1 = PRequest(priority=1, request=Request(url="https://example.com/fast/page"))
            pr2 = PRequest(priority=2, request=Request(url="https://example.com/slow/page"))
            pr3 = PRequest(priority=3, request=Request(url="https://other.com/fast/page"))

            await manager(pr1)
            await manager(pr2)
            await manager(pr3)

            # Should have 2 groups: fast and slow
            assert len(manager._groups) == 2
            assert "fast" in manager._groups
            assert "slow" in manager._groups

            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_rate_limiter_different_intervals_per_group(self, mock_schedule):
        """Test that different groups can have different intervals."""
        call_times_by_group = {"fast": [], "slow": []}

        async def schedule_with_timing(pr: PRequest):
            group = "fast" if "fast" in pr.request.url else "slow"
            call_times_by_group[group].append(asyncio.get_event_loop().time())
            await mock_schedule(pr)

        def custom_group_by(request: Request) -> tuple[Hashable, float]:
            if "fast" in request.url:
                return ("fast", 0.02)
            else:
                return ("slow", 0.1)

        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, group_by=custom_group_by),
            retry_config=RequestRetryConfig(),
            schedule=schedule_with_timing,
        ) as manager:
            for i in range(3):
                await manager(PRequest(priority=i, request=Request(url=f"https://example.com/fast/{i}")))
                await manager(PRequest(priority=i, request=Request(url=f"https://example.com/slow/{i}")))

            await asyncio.sleep(0.5)

            # Verify fast group used smaller interval
            assert len(call_times_by_group["fast"]) == 3
            fast_intervals = [
                call_times_by_group["fast"][i] - call_times_by_group["fast"][i - 1]
                for i in range(1, len(call_times_by_group["fast"]))
            ]
            for interval in fast_intervals:
                assert 0.01 <= interval < 0.08

            # Verify slow group used larger interval
            assert len(call_times_by_group["slow"]) == 3
            slow_intervals = [
                call_times_by_group["slow"][i] - call_times_by_group["slow"][i - 1]
                for i in range(1, len(call_times_by_group["slow"]))
            ]
            for interval in slow_intervals:
                assert interval >= 0.09

    @pytest.mark.asyncio
    async def test_rate_limiter_group_cleanup_after_idle(self, mock_schedule):
        """Test that idle groups are automatically cleaned up."""
        config = RateLimitConfig(enabled=True, default_interval=0.01, cleanup_timeout=0.1)
        async with RateLimitManager(config, retry_config=RequestRetryConfig(), schedule=mock_schedule) as manager:
            pr = PRequest(priority=1, request=Request(url="https://example.com/page"))
            await manager(pr)

            assert "example.com" in manager._groups

            await asyncio.sleep(0.25)

            assert "example.com" not in manager._groups

    @pytest.mark.asyncio
    async def test_rate_limiter_active_property(self, mock_schedule):
        """Test the active property of RateLimitManager."""
        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, default_interval=0.05),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            assert not manager.active

            pr1 = PRequest(priority=1, request=Request(url="https://example.com/1"))
            pr2 = PRequest(priority=2, request=Request(url="https://example.com/2"))

            await manager(pr1)
            await manager(pr2)

            assert manager.active

            await asyncio.sleep(0.2)

            assert not manager.active

    @pytest.mark.asyncio
    async def test_rate_limiter_close_shuts_down_all_groups(self, mock_schedule):
        """Test that closing rate limiter shuts down all groups."""
        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            await manager(PRequest(priority=1, request=Request(url="https://example.com/1")))
            await manager(PRequest(priority=2, request=Request(url="https://other.com/1")))
            await manager(PRequest(priority=3, request=Request(url="https://third.com/1")))

            assert len(manager._groups) == 3

        assert len(manager._groups) == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_zero_interval_adjusted_to_minimum(self, mock_schedule):
        """Test that zero or negative intervals are adjusted to minimum."""

        def zero_interval_group_by(request: Request) -> tuple[Hashable, float]:
            return ("zero", 0.0)

        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, group_by=zero_interval_group_by),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            pr = PRequest(priority=1, request=Request(url="https://example.com/page"))
            await manager(pr)
            # Group should be created with minimum interval
            assert "zero" in manager._groups
            group = manager._groups["zero"]
            assert group._interval == 0.01  # Minimum interval

    @pytest.mark.asyncio
    async def test_rate_limiter_handles_url_without_host(self, mock_schedule):
        """Test that rate limiter handles URLs without a host."""
        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            # Request with relative URL (no host)
            pr = PRequest(priority=1, request=Request(url="/relative/path"))
            await manager(pr)

            # Should create group with "unknown" key
            assert "unknown" in manager._groups

            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_rate_limiter_reuses_existing_groups(self, mock_schedule):
        """Test that rate limiter reuses existing groups for same host."""
        async with RateLimitManager(
            config=RateLimitConfig(enabled=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            pr1 = PRequest(priority=1, request=Request(url="https://example.com/page1"))
            pr2 = PRequest(priority=2, request=Request(url="https://example.com/page2"))
            pr3 = PRequest(priority=3, request=Request(url="https://example.com/page3"))

            await manager(pr1)
            first_group = manager._groups["example.com"]

            await manager(pr2)
            second_group = manager._groups["example.com"]

            await manager(pr3)
            third_group = manager._groups["example.com"]

            assert first_group is second_group
            assert second_group is third_group
            assert len(manager._groups) == 1


class TestDefaultGroupByFactory:
    def test_default_group_by_extracts_hostname(self):
        """Test that default group_by function extracts hostname."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="https://example.com/path?query=1")
        key, interval = group_by(request)

        assert key == "example.com"
        assert interval == 0.3

    def test_default_group_by_handles_port_in_url(self):
        """Test that default group_by handles URLs with ports."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="https://example.com:8080/path")
        key, interval = group_by(request)

        assert key == "example.com"
        assert interval == 0.3

    def test_default_group_by_handles_no_host(self):
        """Test that default group_by handles URLs without host."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="/relative/path")
        key, interval = group_by(request)

        assert key == "unknown"
        assert interval == 0.3

    def test_default_group_by_groups_subdomains_separately(self):
        """Test that different subdomains create different groups."""
        group_by = default_group_by_factory(default_interval=0.3)

        request1 = Request(url="https://api.example.com/endpoint")
        request2 = Request(url="https://www.example.com/page")

        key1, _ = group_by(request1)
        key2, _ = group_by(request2)

        assert key1 == "api.example.com"
        assert key2 == "www.example.com"
        assert key1 != key2
