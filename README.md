# Agent Heartbeat Scheduler

A proactive scheduling and health monitoring system for autonomous AI agents. Agents don't just respond to requests — they wake up on heartbeat intervals, evaluate their environment, decide if action is needed, and execute autonomously.

This is the difference between reactive agents (wait for trigger) and proactive agents (continuously scanning for opportunities).

## Concept

```
Traditional Agent:
    User/Event → Agent responds → Done (sleeps until next trigger)

Heartbeat Agent:
    ┌──────────────────────────────────────────────────┐
    │  Every N minutes:                                 │
    │                                                   │
    │  1. Wake up (heartbeat fires)                     │
    │  2. Check environment (new signals? score changes?)│
    │  3. Evaluate: should I act?                       │
    │  4. If yes → execute action → log outcome         │
    │  5. If no → log "checked, nothing to do"          │
    │  6. Sleep until next heartbeat                    │
    │                                                   │
    │  Health monitor tracks:                           │
    │  • Is the agent alive? (missed heartbeats = dead) │
    │  • Is it acting? (too many no-ops = stuck)        │
    │  • Is it overacting? (too many actions = runaway) │
    └──────────────────────────────────────────────────┘
```

## Why This Matters

Revenue workflows don't wait for user clicks. Leads go cold, opportunities stall, contacts disengage — all silently. Proactive agents detect these signals and act before a human notices:

| Agent | Heartbeat | Checks For | Action |
|---|---|---|---|
| **Research Agent** | Every 4 hours | New news, SEC filings, market signals for tracked companies | Update research context, notify Analysis agent |
| **Scoring Agent** | Every 1 hour | Score threshold crossings (Contact → Lead conversion signals) | Trigger soft conversion, update state machine |
| **Outreach Agent** | Every 30 min | Leads with no touchpoint in 48+ hours, opened-but-not-replied emails | Send follow-up, adjust messaging strategy |
| **Health Monitor** | Every 6 hours | Customer engagement decline, support ticket spikes, NPS drops | Flag at-risk accounts, notify account manager |

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   HEARTBEAT SCHEDULER                   │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Research    │  │  Scoring    │  │  Outreach   │    │
│  │  Heartbeat   │  │  Heartbeat   │  │  Heartbeat   │    │
│  │  ⏱ 4hr       │  │  ⏱ 1hr       │  │  ⏱ 30min     │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │            │
│         ▼                ▼                ▼            │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Execution Engine                    │   │
│  │  • Evaluate preconditions                       │   │
│  │  • Acquire distributed lock (prevent duplicates)│   │
│  │  • Execute agent action                         │   │
│  │  • Log outcome                                  │   │
│  │  • Release lock                                 │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│                         ▼                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Health Monitor                      │   │
│  │  • Track heartbeat regularity                   │   │
│  │  • Detect missed beats (agent down)             │   │
│  │  • Detect stuck agents (all no-ops)             │   │
│  │  • Detect runaway agents (too many actions)     │   │
│  │  • Auto-restart / circuit break / alert         │   │
│  └─────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

## Key Features

### Proactive Scheduling
- **Configurable heartbeat intervals** per agent (30 seconds to 24 hours)
- **Jitter**: Random offset to prevent all agents firing simultaneously
- **Backoff**: If an agent keeps finding nothing to do, gradually increase interval
- **Catchup**: If scheduler was down, process missed heartbeats on restart (configurable)

### Environment Evaluation
- **Precondition checks**: Before acting, evaluate if the environment actually changed
- **Priority queue**: Multiple pending actions → execute highest priority first
- **Dependency awareness**: "Don't run Outreach heartbeat if Research heartbeat hasn't completed today"
- **Cooldown**: Per-contact cooldown to prevent over-contacting a lead

### Distributed Safety
- **Distributed locks**: Prevent duplicate execution in multi-instance deployments
- **Idempotent actions**: Every agent action is designed to be safely re-executed
- **Circuit breaker**: If an agent fails N times in a row, pause its heartbeat and alert

### Health Monitoring
- **Liveness**: Is the agent process alive? (missed 3+ heartbeats = dead)
- **Activity ratio**: What % of heartbeats resulted in action? (too low = stuck, too high = runaway)
- **Error rate**: What % of actions failed? (high = something broke)
- **Latency**: How long does each heartbeat cycle take? (slow = resource issue)

## Project Structure

```
agent-heartbeat-scheduler/
├── README.md
├── requirements.txt
├── scheduler/
│   ├── __init__.py
│   ├── heartbeat.py             # Core heartbeat timer with jitter/backoff
│   ├── execution_engine.py      # Precondition eval + distributed lock + execute
│   ├── priority_queue.py        # Multi-action prioritization
│   └── config.py                # Per-agent heartbeat configuration
├── health/
│   ├── __init__.py
│   ├── monitor.py               # Agent health tracking
│   ├── circuit_breaker.py       # Auto-pause on repeated failures
│   ├── alerting.py              # Slack/PagerDuty alerts
│   └── dashboard.py             # Real-time health dashboard data
├── agents/
│   ├── __init__.py
│   ├── base_heartbeat_agent.py  # Abstract proactive agent interface
│   ├── research_heartbeat.py    # Periodic research refresh
│   ├── scoring_heartbeat.py     # Periodic score recalculation
│   └── outreach_heartbeat.py    # Periodic follow-up check
├── locks/
│   ├── __init__.py
│   ├── redis_lock.py            # Distributed lock via Redis
│   └── idempotency.py           # Idempotency key management
├── tests/
│   ├── test_heartbeat.py
│   ├── test_circuit_breaker.py
│   ├── test_health_monitor.py
│   └── test_distributed_lock.py
└── examples/
    └── revenue_pipeline_heartbeats.py
```

## Usage

```python
from scheduler import HeartbeatScheduler
from agents import ResearchHeartbeat, ScoringHeartbeat, OutreachHeartbeat
from health import HealthMonitor

scheduler = HeartbeatScheduler()

# Register agents with their heartbeat configs
scheduler.register(
    ResearchHeartbeat(
        interval_minutes=240,
        jitter_minutes=30,
        backoff_factor=1.5,
        max_interval_minutes=480,
    )
)

scheduler.register(
    ScoringHeartbeat(
        interval_minutes=60,
        jitter_minutes=10,
        dependencies=["research"],  # Don't run if research hasn't run today
    )
)

scheduler.register(
    OutreachHeartbeat(
        interval_minutes=30,
        jitter_minutes=5,
        cooldown_per_contact_hours=48,  # Don't re-contact within 48h
        max_actions_per_cycle=10,       # Cap to prevent runaway
    )
)

# Start health monitoring
monitor = HealthMonitor(scheduler)
monitor.start(
    check_interval_seconds=60,
    alert_on_missed_beats=3,
    alert_channel="slack:#agent-health",
)

# Start all heartbeats
scheduler.start()
```

## Design Decisions

- **Heartbeat, not event-driven**: Event-driven agents miss slow-burn signals (lead gradually going cold over 2 weeks). Heartbeats periodically re-evaluate the full picture.
- **Jitter prevents thundering herd**: Without jitter, 50 agents all fire at :00 and overload the LLM endpoint. Random offset spreads the load.
- **Adaptive backoff**: An outreach agent checking a quiet lead pool every 30 minutes wastes resources. Backoff increases the interval when there's consistently nothing to do — and resets when activity resumes.
- **Circuit breaker over retry**: Infinite retries on a broken agent waste resources and can cause cascading failures. Circuit breaker pauses the agent, alerts a human, and waits for manual reset.

