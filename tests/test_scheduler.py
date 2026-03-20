import asyncio
import time
import pytest
from core.scheduler import HeartbeatScheduler, HeartbeatConfig, CircuitBreaker, HeartbeatStats


class TestCircuitBreaker:
    def test_closed_by_default(self):
        cb = CircuitBreaker(fail_limit=3)
        assert not cb.is_open("agent1")

    def test_opens_at_limit(self):
        cb = CircuitBreaker(fail_limit=3, cooldown_sec=60)
        for _ in range(3):
            cb.record_failure("agent1")
        assert cb.is_open("agent1")

    def test_success_resets(self):
        cb = CircuitBreaker(fail_limit=3)
        cb.record_failure("agent1")
        cb.record_failure("agent1")
        cb.record_success("agent1")
        cb.record_failure("agent1")
        assert not cb.is_open("agent1")

    def test_independent_agents(self):
        cb = CircuitBreaker(fail_limit=2, cooldown_sec=60)
        cb.record_failure("a")
        cb.record_failure("a")
        assert cb.is_open("a")
        assert not cb.is_open("b")

    def test_recovers_after_cooldown(self):
        cb = CircuitBreaker(fail_limit=1, cooldown_sec=0)
        cb.record_failure("a")
        # Cooldown is 0 seconds, so it should recover immediately
        # Force check which clears expired cooldown
        time.sleep(0.05)
        result = cb.is_open("a")
        assert not result


class TestHeartbeatStats:
    def test_activity_rate(self):
        s = HeartbeatStats(beats=10, actions=4)
        assert s.activity_rate == 0.4

    def test_error_rate(self):
        s = HeartbeatStats(beats=10, errors=2)
        assert s.error_rate == 0.2

    def test_zero_beats(self):
        s = HeartbeatStats()
        assert s.activity_rate == 0
        assert s.error_rate == 0


class TestCooldown:
    def test_entity_not_in_cooldown(self):
        sched = HeartbeatScheduler()
        sched.register(HeartbeatConfig("agent1", 1.0, cooldown_per_entity_sec=10), lambda: True)
        assert not sched.check_cooldown("agent1", "entity_123")

    def test_entity_in_cooldown(self):
        sched = HeartbeatScheduler()
        sched.register(HeartbeatConfig("agent1", 1.0, cooldown_per_entity_sec=60), lambda: True)
        sched.record_entity_action("agent1", "entity_123")
        assert sched.check_cooldown("agent1", "entity_123")

    def test_no_cooldown_configured(self):
        sched = HeartbeatScheduler()
        sched.register(HeartbeatConfig("agent1", 1.0, cooldown_per_entity_sec=0), lambda: True)
        sched.record_entity_action("agent1", "entity_123")
        assert not sched.check_cooldown("agent1", "entity_123")


class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_runs_and_stops(self):
        sched = HeartbeatScheduler()
        call_count = 0
        async def handler():
            nonlocal call_count
            call_count += 1
            return True
        sched.register(HeartbeatConfig("test", interval_sec=0.05), handler)
        sched.start()
        await asyncio.sleep(0.3)
        await sched.stop()
        assert call_count > 0
        stats = sched.all_stats["test"]
        assert stats["beats"] > 0

    @pytest.mark.asyncio
    async def test_backoff_increases_interval(self):
        sched = HeartbeatScheduler()
        async def noop():
            return False
        sched.register(HeartbeatConfig("lazy", interval_sec=0.05, backoff_factor=2.0, max_interval_sec=1.0), noop)
        sched.start()
        await asyncio.sleep(0.5)
        await sched.stop()
        assert sched._stats["lazy"].current_interval > 0.05

    @pytest.mark.asyncio
    async def test_error_triggers_circuit_breaker(self):
        sched = HeartbeatScheduler()
        sched.breaker.fail_limit = 2
        async def failing():
            raise RuntimeError("boom")
        sched.register(HeartbeatConfig("fail", interval_sec=0.05), failing)
        sched.start()
        await asyncio.sleep(0.4)
        await sched.stop()
        stats = sched.all_stats["fail"]
        assert stats["errors"] > 0
