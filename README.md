# 28 · botkit

Async bot framework with routers, middleware and FSM state.

## Run

```bash
python -m botkit  (or from botkit.core import Bot)
```

## Test

```bash
pytest projects/28-telegram-bot -q
```

## What it demonstrates

- Command router plus finite-state handlers for multi-step conversations
- Middleware chain that can log, rate-limit and short-circuit
- Transport abstraction: a memory transport records messages for tests
- Per-chat state store, ready to be swapped for Redis

## Repository
- GitHub: https://github.com/{owner}/telegram-bot-framework
- Python 3.11+ · tests: `pytest` · runtime dependencies: none (standard library only)
