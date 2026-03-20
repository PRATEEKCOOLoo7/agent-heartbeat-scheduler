"""Agent Heartbeat Scheduler — Demo"""

import asyncio
import logging
import random
from core.scheduler import HeartbeatScheduler, HeartbeatConfig, CircuitBreaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s: %(message)s", datefmt="%H:%M:%S")


async def research_check():
    acted = random.random() > 0.6
    if acted:
        logging.info("[research] found new signals — updating context")
    return acted

async def scoring_check():
    acted = random.random() > 0.4
    if acted:
        logging.info("[scoring] recalculated scores — 2 contacts crossed threshold")
    return acted

async def outreach_check():
    acted = random.random() > 0.5
    if acted:
        logging.info("[outreach] sent follow-up to stale lead")
    return acted


async def main():
    print(f"\n{'='*60}")
    print("  Agent Heartbeat Scheduler — Demo")
    print("  Running 3 agents for 5 seconds")
    print(f"{'='*60}\n")

    sched = HeartbeatScheduler()
    sched.register(HeartbeatConfig("research", interval_sec=0.8, jitter_sec=0.2, backoff_factor=1.3), research_check)
    sched.register(HeartbeatConfig("scoring", interval_sec=0.5, jitter_sec=0.1), scoring_check)
    sched.register(HeartbeatConfig("outreach", interval_sec=0.6, jitter_sec=0.15, cooldown_per_entity_sec=2.0), outreach_check)

    sched.start()
    await asyncio.sleep(5)
    await sched.stop()

    print(f"\n  Stats:")
    for name, stats in sched.all_stats.items():
        print(f"    {name:12s} beats={stats['beats']:2d} actions={stats['actions']:2d} "
              f"noops={stats['noops']:2d} errors={stats['errors']} "
              f"activity={stats['activity_rate']:.0%}")

    print(f"\n{'='*60}")
    print("  Demo complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
