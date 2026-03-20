"""Agent heartbeat scheduler with jitter, backoff, cooldown, and circuit breaker.

Agents wake on configurable intervals, evaluate their environment,
decide whether to act, and either execute or skip. Health monitoring
tracks liveness, activity rates, and error rates.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

log = logging.getLogger(__name__)


@dataclass
class HeartbeatConfig:
    name: str
    interval_sec: float
    jitter_sec: float = 0.0
    backoff_factor: float = 1.0
    max_interval_sec: float = 3600.0
    max_actions_per_cycle: int = 50
    cooldown_per_entity_sec: float = 0.0


@dataclass
class HeartbeatStats:
    beats: int = 0
    actions: int = 0
    noops: int = 0
    errors: int = 0
    consecutive_noops: int = 0
    current_interval: float = 0.0
    last_beat: float = 0.0

    @property
    def activity_rate(self) -> float:
        return self.actions / self.beats if self.beats else 0

    @property
    def error_rate(self) -> float:
        return self.errors / self.beats if self.beats else 0


class CircuitBreaker:
    def __init__(self, fail_limit: int = 5, cooldown_sec: int = 120):
        self.fail_limit = fail_limit
        self.cooldown_sec = cooldown_sec
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def record_failure(self, name: str):
        self._failures[name] = self._failures.get(name, 0) + 1
        if self._failures[name] >= self.fail_limit:
            self._open_until[name] = time.monotonic() + self.cooldown_sec
            log.critical(f"CIRCUIT OPEN: {name}")

    def record_success(self, name: str):
        self._failures[name] = 0

    def is_open(self, name: str) -> bool:
        deadline = self._open_until.get(name)
        if not deadline:
            return False
        if time.monotonic() > deadline:
            del self._open_until[name]
            self._failures[name] = 0
            return False
        return True


class HeartbeatScheduler:
    def __init__(self):
        self._configs: dict[str, HeartbeatConfig] = {}
        self._stats: dict[str, HeartbeatStats] = {}
        self._handlers: dict[str, Callable] = {}
        self._cooldowns: dict[str, dict[str, float]] = {}
        self.breaker = CircuitBreaker()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def register(self, config: HeartbeatConfig, handler: Callable):
        self._configs[config.name] = config
        self._stats[config.name] = HeartbeatStats(current_interval=config.interval_sec)
        self._handlers[config.name] = handler
        self._cooldowns[config.name] = {}

    def check_cooldown(self, agent: str, entity_id: str) -> bool:
        cfg = self._configs.get(agent)
        if not cfg or cfg.cooldown_per_entity_sec <= 0:
            return False
        last = self._cooldowns.get(agent, {}).get(entity_id, 0)
        return (time.monotonic() - last) < cfg.cooldown_per_entity_sec

    def record_entity_action(self, agent: str, entity_id: str):
        self._cooldowns.setdefault(agent, {})[entity_id] = time.monotonic()

    async def _loop(self, name: str):
        cfg = self._configs[name]
        stats = self._stats[name]

        while self._running:
            jitter = random.uniform(0, cfg.jitter_sec) if cfg.jitter_sec > 0 else 0
            await asyncio.sleep(stats.current_interval + jitter)

            if self.breaker.is_open(name):
                log.warning(f"[{name}] circuit open — skipping")
                continue

            stats.beats += 1
            stats.last_beat = time.monotonic()

            try:
                result = await self._handlers[name]()
                acted = bool(result)

                if acted:
                    stats.actions += 1
                    stats.consecutive_noops = 0
                    stats.current_interval = cfg.interval_sec
                    self.breaker.record_success(name)
                else:
                    stats.noops += 1
                    stats.consecutive_noops += 1
                    if cfg.backoff_factor > 1.0:
                        stats.current_interval = min(
                            stats.current_interval * cfg.backoff_factor,
                            cfg.max_interval_sec,
                        )
            except Exception as e:
                stats.errors += 1
                self.breaker.record_failure(name)
                log.error(f"[{name}] heartbeat error: {e}")

    def start(self):
        self._running = True
        for name in self._configs:
            self._tasks.append(asyncio.create_task(self._loop(name)))

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    @property
    def all_stats(self) -> dict[str, dict]:
        return {
            n: {"beats": s.beats, "actions": s.actions, "noops": s.noops,
                "errors": s.errors, "activity_rate": round(s.activity_rate, 3),
                "error_rate": round(s.error_rate, 3),
                "interval": round(s.current_interval, 1)}
            for n, s in self._stats.items()
        }
