from __future__ import annotations

import asyncio

import pytest

from botkit.core import (
    Bot,
    Context,
    MemoryTransport,
    StateStore,
    Update,
    logging_middleware,
    rate_limit_middleware,
)


def build() -> tuple[Bot, MemoryTransport]:
    transport = MemoryTransport()
    bot = Bot(transport=transport)

    @bot.command("start")
    async def start(update: Update, ctx: Context) -> None:
        ctx.state.set(update.chat_id, "awaiting_name")
        await ctx.reply(update, "What is your name?")

    @bot.on_state("awaiting_name")
    async def save_name(update: Update, ctx: Context) -> None:
        ctx.state.set(update.chat_id, "idle", name=update.text.strip())
        await ctx.reply(update, f"Nice to meet you, {update.text.strip()}")

    @bot.command("whoami")
    async def whoami(update: Update, ctx: Context) -> None:
        name = ctx.state.payload(update.chat_id).get("name", "stranger")
        await ctx.reply(update, f"You are {name}")

    @bot.command("reset")
    async def reset(update: Update, ctx: Context) -> None:
        ctx.state.clear(update.chat_id)
        await ctx.reply(update, "State cleared")

    @bot.fallback
    async def unknown(update: Update, ctx: Context) -> None:
        await ctx.reply(update, "I do not understand")

    return bot, transport


def test_update_parses_command_and_args():
    update = Update(1, "/start@kitab_bot hello world")
    assert update.command == "start"
    assert update.args == "hello world"


def test_update_without_command():
    assert Update(1, "hello").command is None


def test_command_handler():
    bot, transport = build()
    bot.run([Update(10, "/start")])
    assert transport.last == "What is your name?"
    assert bot.state.get(10) == "awaiting_name"


def test_fsm_consumes_the_next_message():
    bot, transport = build()
    bot.run([Update(10, "/start"), Update(10, "Ada")])
    assert transport.last == "Nice to meet you, Ada"
    assert bot.state.payload(10)["name"] == "Ada"


def test_state_cleared_after_leaving_fsm():
    bot, transport = build()
    bot.run([Update(10, "/start"), Update(10, "Ada"), Update(10, "/whoami")])
    assert transport.last == "You are Ada"


def test_reset_clears_state():
    bot, transport = build()
    bot.run([Update(10, "/start"), Update(10, "/reset"), Update(10, "/whoami")])
    assert transport.last == "You are stranger"


def test_fallback():
    bot, transport = build()
    bot.run([Update(1, "blah")])
    assert transport.last == "I do not understand"


def test_states_are_per_chat():
    bot, transport = build()
    asyncio.run(bot.handle(Update(1, "/start")))
    asyncio.run(bot.handle(Update(2, "plain message")))
    assert transport.sent[-1][1] == "I do not understand"
    assert bot.state.get(1) == "awaiting_name"


def test_middleware_runs_in_order_and_can_short_circuit():
    bot, transport = build()
    log: list[Update] = []
    blocked: list[Update] = []

    async def block(update: Update) -> None:
        blocked.append(update)

    bot.use(logging_middleware(log))
    bot.use(rate_limit_middleware(max_per_chat=1, replay=block))
    bot.run([Update(5, "/start"), Update(5, "/start")])
    assert len(log) == 2
    assert len(blocked) == 1
    assert transport.last == "What is your name?"


def test_command_names_are_case_insensitive():
    bot, transport = build()
    bot.run([Update(1, "/START")])
    assert transport.last == "What is your name?"


def test_unhandled_command_falls_back():
    bot, transport = build()
    bot.run([Update(1, "/nope")])
    assert transport.last == "I do not understand"


def test_state_store_isolated():
    store = StateStore()
    store.set(1, "s", a=1)
    store.set(1, "t", b=2)
    assert store.payload(1) == {"a": 1, "b": 2}
    store.clear(1)
    assert store.get(1) is None and store.payload(1) == {}
