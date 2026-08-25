import asyncio
from typing import Hashable
from unittest.mock import AsyncMock

import pytest

from aioscraper.config import RateLimitConfig, RequestRetryConfig
from aioscraper.core.rate_limiter import RateLimitManager, RequestGroup, default_group_by_factory
from aioscraper.types import GroupPolicy
from aioscraper.types.session import Attempt, Request
from tests.helpers import wait_and_settle, wait_for


@pytest.fixture
def mock_schedule():
    "Stands in for the scheduler, with the request finishing at once and giving its permit back."

    async def schedule(attempt: Attempt):
        attempt.release_permit()

    return AsyncMock(side_effect=schedule)


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

        async def schedule_with_timing(attempt: Attempt):
            call_times.append(asyncio.get_event_loop().time())
            await mock_schedule(attempt)

        group = RequestGroup(
            key="test-group",
            interval=interval,
            cleanup_timeout=1.0,
            schedule=schedule_with_timing,
            on_finished=on_finished,
        )
        group.start_listening()

        attempt1 = Attempt(priority=1, request=Request(url="https://example.com/1"))
        attempt2 = Attempt(priority=2, request=Request(url="https://example.com/2"))
        attempt3 = Attempt(priority=3, request=Request(url="https://example.com/3"))

        await group.put(attempt1)
        await group.put(attempt2)
        await group.put(attempt3)

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

        attempt = Attempt(priority=1, request=Request(url="https://example.com/idle"))
        await group.put(attempt)

        await asyncio.sleep(0.05)
        assert mock_schedule.call_count == 1

        await asyncio.sleep(cleanup_timeout + 0.1)

        # exactly once: the idle exit is reported by the worker's done callback and nothing else
        assert calls == [("finished", "idle-group")]
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

        async def failing_schedule(attempt: Attempt):
            error = RuntimeError(f"Failed to schedule {attempt.request.url}")
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

        attempt = Attempt(priority=1, request=Request(url="https://example.com/fail"))
        await group.put(attempt)

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

        attempt = Attempt(priority=1, request=Request(url="https://example.com/active"))
        await group.put(attempt)

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


class TestGroupConcurrency:
    @staticmethod
    def _held_schedule() -> tuple[AsyncMock, list[Attempt]]:
        "A schedule that keeps every attempt in flight until the test finishes it by hand."
        in_flight: list[Attempt] = []

        async def schedule(attempt: Attempt):
            in_flight.append(attempt)

        return AsyncMock(side_effect=schedule), in_flight

    @staticmethod
    def _group(schedule, on_finished, concurrency: int, interval: float = 0.001) -> RequestGroup:
        group = RequestGroup(
            key="capped",
            interval=interval,
            cleanup_timeout=10.0,
            schedule=schedule,
            on_finished=on_finished,
            concurrency=concurrency,
        )
        group.start_listening()
        return group

    @pytest.mark.asyncio
    async def test_group_dispatches_no_more_than_its_ceiling(self, on_group_finished_factory):
        """Test that a group hands off at most `concurrency` attempts before one finishes."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=2)

        for priority in range(5):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        await wait_and_settle(lambda: len(in_flight) == 2)

        in_flight[0].release_permit()
        await wait_and_settle(lambda: len(in_flight) == 3)

        in_flight[1].release_permit()
        in_flight[2].release_permit()
        await wait_and_settle(lambda: len(in_flight) == 5)

        await group.close()

    @pytest.mark.asyncio
    async def test_group_without_ceiling_dispatches_everything(self, on_group_finished_factory):
        """Test that concurrency=0 leaves the group unbounded."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=0)

        for priority in range(5):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        await wait_for(lambda: len(in_flight) == 5)

        await group.close()

    @pytest.mark.asyncio
    async def test_permit_released_once_per_attempt(self, on_group_finished_factory):
        """Test that releasing an attempt twice does not hand its group a permit out of thin air."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=1)

        for priority in range(3):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        await wait_and_settle(lambda: len(in_flight) == 1)

        attempt = in_flight[0]
        attempt.release_permit()
        attempt.release_permit()
        attempt.release_permit()

        # a permit per release would have let both remaining attempts through
        await wait_and_settle(lambda: len(in_flight) == 2)

        await group.close()

    @pytest.mark.asyncio
    async def test_failed_schedule_gives_the_permit_back(self, on_group_finished_factory):
        """Test that a schedule that raises does not cost the group a permit forever."""
        scheduled: list[Attempt] = []

        async def schedule(attempt: Attempt):
            scheduled.append(attempt)
            raise RuntimeError("spawn failed")

        group = self._group(AsyncMock(side_effect=schedule), on_group_finished_factory(), concurrency=1)

        for priority in range(3):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        await wait_for(lambda: len(scheduled) == 3)
        await wait_for(lambda: group.in_flight == 0)

        await group.close()

    @pytest.mark.asyncio
    async def test_group_stays_active_while_an_attempt_waits_for_a_permit(self, on_group_finished_factory):
        """Test that a group holding a dispatched attempt is not idle, queue empty or not."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=1)

        await group.put(Attempt(priority=1, request=Request(url="https://example.com/page")))
        await group.put(Attempt(priority=2, request=Request(url="https://example.com/page")))

        # one dispatched, one popped and waiting on the permit: nothing is left in the queue
        await wait_for(group._queue.empty)
        assert group.active

        in_flight[0].release_permit()
        await wait_for(lambda: len(in_flight) == 2)
        assert group.active

        in_flight[1].release_permit()
        await wait_for(lambda: not group.active)

        await group.close()

    @pytest.mark.asyncio
    async def test_idle_timeout_does_not_collect_a_group_in_flight(self):
        """Test that a group is not retired while its requests are still running."""
        finished: list[Hashable] = []
        schedule, in_flight = self._held_schedule()

        group = RequestGroup(
            key="in-flight",
            interval=0.001,
            cleanup_timeout=0.05,
            schedule=schedule,
            on_finished=lambda key, _: finished.append(key),
            concurrency=1,
        )
        group.start_listening()

        await group.put(Attempt(priority=1, request=Request(url="https://example.com/page")))
        await wait_for(lambda: len(in_flight) == 1)

        # well past the idle timeout, but the request has not come back yet
        await asyncio.sleep(0.3)
        assert finished == []

        in_flight[0].release_permit()
        await wait_for(lambda: finished == ["in-flight"])

        await group.close()

    @pytest.mark.asyncio
    async def test_finished_attempts_let_the_next_ones_through(self, on_group_finished_factory):
        """Test that released permits are handed straight to the attempts waiting behind them."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=2)

        for priority in range(4):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        await wait_and_settle(lambda: len(in_flight) == 2)

        for attempt in tuple(in_flight):
            attempt.release_permit()

        await wait_and_settle(lambda: len(in_flight) == 4)
        assert group.in_flight == 2

        await group.close()

    @pytest.mark.asyncio
    async def test_close_releases_what_the_group_still_holds(self, on_group_finished_factory):
        """Test that close() reclaims the permits of attempts whose jobs never came back."""
        schedule, in_flight = self._held_schedule()
        group = self._group(schedule, on_group_finished_factory(), concurrency=2)

        for priority in range(4):
            await group.put(Attempt(priority=priority, request=Request(url="https://example.com/page")))

        # two dispatched and never finished, one held by the worker waiting for a permit
        await wait_for(lambda: group.in_flight == 3)
        assert len(in_flight) == 2

        await group.close()

        assert group.in_flight == 0
        assert group._permits is not None
        assert group._permits._value == 2


class TestRateLimitManager:
    @pytest.mark.asyncio
    async def test_rate_limiter_groups_by_hostname(self, mock_schedule):
        """Test that rate limiter groups requests by hostname when enabled."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.05),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            attempt1 = Attempt(priority=1, request=Request(url="https://example.com/page1"))
            attempt2 = Attempt(priority=2, request=Request(url="https://example.com/page2"))
            attempt3 = Attempt(priority=3, request=Request(url="https://other.com/page1"))

            await manager(attempt1)
            await manager(attempt2)
            await manager(attempt3)

            assert len(manager._groups) == 2
            assert "example.com" in manager._groups
            assert "other.com" in manager._groups

            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_rate_limiter_disabled_applies_simple_delay(self, mock_schedule):
        """Test that disabled rate limiter still applies default_interval."""
        call_times = []
        default_interval = 0.05

        async def schedule_with_timing(attempt: Attempt):
            call_times.append(asyncio.get_event_loop().time())
            await mock_schedule(attempt)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=False, default_interval=default_interval),
            retry_config=RequestRetryConfig(),
            schedule=schedule_with_timing,
        ) as manager:
            attempt1 = Attempt(priority=1, request=Request(url="https://example.com/1"))
            attempt2 = Attempt(priority=2, request=Request(url="https://example.com/2"))

            await manager(attempt1)
            await manager(attempt2)

            assert len(manager._groups) == 0

            # Verify calls and timing
            assert len(call_times) == 2
            elapsed = call_times[1] - call_times[0]
            assert elapsed >= default_interval - 0.01

    @pytest.mark.asyncio
    async def test_rate_limiter_custom_group_by(self, mock_schedule):
        """Test rate limiter with custom group_by function."""

        def custom_group_by(request: Request) -> GroupPolicy:
            # Group by path and use different intervals
            if "fast" in request.url:
                return GroupPolicy("fast", 0.01)

            return GroupPolicy("slow", 0.05)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True),
            group_by=custom_group_by,
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            attempt1 = Attempt(priority=1, request=Request(url="https://example.com/fast/page"))
            attempt2 = Attempt(priority=2, request=Request(url="https://example.com/slow/page"))
            attempt3 = Attempt(priority=3, request=Request(url="https://other.com/fast/page"))

            await manager(attempt1)
            await manager(attempt2)
            await manager(attempt3)

            # Should have 2 groups: fast and slow
            assert len(manager._groups) == 2
            assert "fast" in manager._groups
            assert "slow" in manager._groups

            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_rate_limiter_different_intervals_per_group(self, mock_schedule):
        """Test that different groups can have different intervals."""
        call_times_by_group = {"fast": [], "slow": []}

        async def schedule_with_timing(attempt: Attempt):
            group = "fast" if "fast" in attempt.request.url else "slow"
            call_times_by_group[group].append(asyncio.get_event_loop().time())
            await mock_schedule(attempt)

        def custom_group_by(request: Request) -> GroupPolicy:
            if "fast" in request.url:
                return GroupPolicy("fast", 0.02)
            else:
                return GroupPolicy("slow", 0.1)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True),
            group_by=custom_group_by,
            retry_config=RequestRetryConfig(),
            schedule=schedule_with_timing,
        ) as manager:
            for i in range(3):
                await manager(Attempt(priority=i, request=Request(url=f"https://example.com/fast/{i}")))
                await manager(Attempt(priority=i, request=Request(url=f"https://example.com/slow/{i}")))

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
        config = RateLimitConfig(per_group=True, default_interval=0.01, cleanup_timeout=0.1)
        async with RateLimitManager(config, retry_config=RequestRetryConfig(), schedule=mock_schedule) as manager:
            attempt = Attempt(priority=1, request=Request(url="https://example.com/page"))
            await manager(attempt)

            assert "example.com" in manager._groups

            await asyncio.sleep(0.25)

            assert "example.com" not in manager._groups

    @pytest.mark.asyncio
    async def test_rate_limiter_active_property(self, mock_schedule):
        """Test the active property of RateLimitManager."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.05),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            assert not manager.active

            attempt1 = Attempt(priority=1, request=Request(url="https://example.com/1"))
            attempt2 = Attempt(priority=2, request=Request(url="https://example.com/2"))

            await manager(attempt1)
            await manager(attempt2)

            assert manager.active

            await asyncio.sleep(0.2)

            assert not manager.active

    @pytest.mark.asyncio
    async def test_rate_limiter_close_shuts_down_all_groups(self, mock_schedule):
        """Test that closing rate limiter shuts down all groups."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/1")))
            await manager(Attempt(priority=2, request=Request(url="https://other.com/1")))
            await manager(Attempt(priority=3, request=Request(url="https://third.com/1")))

            assert len(manager._groups) == 3

        assert len(manager._groups) == 0

    @pytest.mark.asyncio
    async def test_a_group_whose_worker_is_gone_is_replaced(self, mock_schedule):
        """Test that a request never lands in a group with nothing left to read its queue.

        close() reproduces the window: it kills the worker and, the task being canceled rather
        than finished, reports nothing.
        """
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.001),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/1")))
            await wait_for(lambda: mock_schedule.call_count == 1)

            retired = manager._groups["example.com"]
            await retired.close()
            assert not retired.worker_alive
            assert manager._groups["example.com"] is retired

            await manager(Attempt(priority=2, request=Request(url="https://example.com/2")))

            await wait_for(lambda: mock_schedule.call_count == 2)
            assert manager._groups["example.com"] is not retired

    @pytest.mark.asyncio
    async def test_group_concurrency_comes_from_the_config(self, mock_schedule):
        """Test that a group_by leaving concurrency unset takes the configured ceiling."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.01, group_concurrency=4),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/1")))

            assert manager._groups["example.com"].concurrency == 4

    @pytest.mark.asyncio
    async def test_group_by_overrides_the_configured_concurrency(self, mock_schedule):
        """Test that a policy naming its own concurrency wins over the config, zero included."""

        def group_by(request: Request) -> GroupPolicy:
            if "capped" in request.url:
                return GroupPolicy("capped", 0.01, 2)

            return GroupPolicy("uncapped", 0.01, 0)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, group_concurrency=4),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
            group_by=group_by,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/capped")))
            await manager(Attempt(priority=2, request=Request(url="https://example.com/free")))

            assert manager._groups["capped"].concurrency == 2
            assert manager._groups["uncapped"].concurrency == 0

    @pytest.mark.asyncio
    async def test_invalid_concurrency_falls_back_to_the_config(self, mock_schedule, caplog):
        """Test that a negative concurrency is reported and does not remove the ceiling."""

        def group_by(request: Request) -> GroupPolicy:
            return GroupPolicy("broken", 0.01, -5)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, group_concurrency=4),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
            group_by=group_by,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/1")))

            assert manager._groups["broken"].concurrency == 4
            assert "Invalid concurrency -5" in caplog.text

    @pytest.mark.asyncio
    async def test_concurrency_change_for_a_live_group_is_reported(self, mock_schedule, caplog):
        """Test that a live group keeps its ceiling and says so."""
        ceilings = iter((2, 8))

        def group_by(request: Request) -> GroupPolicy:
            return GroupPolicy("live", 0.01, next(ceilings))

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
            group_by=group_by,
        ) as manager:
            await manager(Attempt(priority=1, request=Request(url="https://example.com/1")))
            await manager(Attempt(priority=2, request=Request(url="https://example.com/2")))

            assert manager._groups["live"].concurrency == 2
            assert "runs with concurrency=2" in caplog.text

    @pytest.mark.asyncio
    async def test_rate_limiter_zero_interval_adjusted_to_minimum(self, mock_schedule):
        """Test that zero or negative intervals are adjusted to minimum."""

        def zero_interval_group_by(request: Request) -> GroupPolicy:
            return GroupPolicy("zero", 0.0)

        async with RateLimitManager(
            config=RateLimitConfig(per_group=True),
            group_by=zero_interval_group_by,
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            attempt = Attempt(priority=1, request=Request(url="https://example.com/page"))
            await manager(attempt)
            # Group should be created with minimum interval
            assert "zero" in manager._groups
            group = manager._groups["zero"]
            assert group._interval == 0.01  # Minimum interval

    @pytest.mark.asyncio
    async def test_rate_limiter_handles_url_without_host(self, mock_schedule):
        """Test that rate limiter handles URLs without a host."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            # Request with relative URL (no host)
            attempt = Attempt(priority=1, request=Request(url="/relative/path"))
            await manager(attempt)

            # Should create group with "unknown" key
            assert "unknown" in manager._groups

            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_rate_limiter_reuses_existing_groups(self, mock_schedule):
        """Test that rate limiter reuses existing groups for same host."""
        async with RateLimitManager(
            config=RateLimitConfig(per_group=True, default_interval=0.01),
            retry_config=RequestRetryConfig(),
            schedule=mock_schedule,
        ) as manager:
            attempt1 = Attempt(priority=1, request=Request(url="https://example.com/page1"))
            attempt2 = Attempt(priority=2, request=Request(url="https://example.com/page2"))
            attempt3 = Attempt(priority=3, request=Request(url="https://example.com/page3"))

            await manager(attempt1)
            first_group = manager._groups["example.com"]

            await manager(attempt2)
            second_group = manager._groups["example.com"]

            await manager(attempt3)
            third_group = manager._groups["example.com"]

            assert first_group is second_group
            assert second_group is third_group
            assert len(manager._groups) == 1


class TestDefaultGroupByFactory:
    def test_default_group_by_extracts_hostname(self):
        """Test that default group_by function extracts hostname."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="https://example.com/path?query=1")
        key, interval, concurrency = group_by(request)

        assert key == "example.com"
        assert interval == 0.3
        assert concurrency is None  # the default grouping defers to RateLimitConfig

    def test_default_group_by_handles_port_in_url(self):
        """Test that default group_by handles URLs with ports."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="https://example.com:8080/path")
        key, interval, concurrency = group_by(request)

        assert key == "example.com"
        assert interval == 0.3
        assert concurrency is None  # the default grouping defers to RateLimitConfig

    def test_default_group_by_handles_no_host(self):
        """Test that default group_by handles URLs without host."""
        group_by = default_group_by_factory(default_interval=0.3)

        request = Request(url="/relative/path")
        key, interval, concurrency = group_by(request)

        assert key == "unknown"
        assert interval == 0.3
        assert concurrency is None  # the default grouping defers to RateLimitConfig

    def test_default_group_by_groups_subdomains_separately(self):
        """Test that different subdomains create different groups."""
        group_by = default_group_by_factory(default_interval=0.3)

        request1 = Request(url="https://api.example.com/endpoint")
        request2 = Request(url="https://www.example.com/page")

        key1, _, _ = group_by(request1)
        key2, _, _ = group_by(request2)

        assert key1 == "api.example.com"
        assert key2 == "www.example.com"
        assert key1 != key2
