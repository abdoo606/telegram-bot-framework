"""Framework internals kept deliberately small and fully testable offline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol


@dataclass(slots=True, frozen=True)
class Update:
    chat_id: int
    text: str
    user_id: int = 0

    @property
    def command(self) -> str | None:
        if self.text.startswith("/"):
            return self.text.split()[0][1:].split("@")[0].lower()
        return None

    @property
    def args(self) -> str:
        parts = self.text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""


class Transport(Protocol):
    async def send(self, chat_id: int, text: str) -> None: ...


class MemoryTransport:
    """Records messages instead of calling Telegram - the test double for the whole suite."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    @property
    def last(self) -> str:
        return self.sent[-1][1] if self.sent else ""


Handler = Callable[[Update, "Context"], Awaitable[None]]
Middleware = Callable[[Update, Callable[[Update], Awaitable[None]]], Awaitable[None]]


@dataclass(slots=True)
class Context:
    transport: Transport
    state: "StateStore"
    data: dict[str, object] = field(default_factory=dict)

    async def reply(self, update: Update, text: str) -> None:
        await self.transport.send(update.chat_id, text)


@dataclass(slots=True)
class StateStore:
    """Per-chat FSM state. In production this lives in Redis with a TTL."""

    states: dict[int, str] = field(default_factory=dict)
    payloads: dict[int, dict[str, object]] = field(default_factory=dict)

    def get(self, chat_id: int) -> str | None:
        return self.states.get(chat_id)

    def set(self, chat_id: int, state: str, **payload: object) -> None:
        self.states[chat_id] = state
        self.payloads.setdefault(chat_id, {}).update(payload)

    def clear(self, chat_id: int) -> None:
        self.states.pop(chat_id, None)
        self.payloads.pop(chat_id, None)

    def payload(self, chat_id: int) -> dict[str, object]:
        return self.payloads.get(chat_id, {})


@dataclass(slots=True)
class Bot:
    transport: Transport
    state: StateStore = field(default_factory=StateStore)
    commands: dict[str, Handler] = field(default_factory=dict)
    state_handlers: dict[str, Handler] = field(default_factory=dict)
    fallback_handler: Handler | None = None
    middlewares: list[Middleware] = field(default_factory=list)

    def command(self, name: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.commands[name.lower()] = handler
            return handler

        return register

    def on_state(self, state: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.state_handlers[state] = handler
            return handler

        return register

    def fallback(self, handler: Handler) -> Handler:
        """Register the handler used when nothing else matches."""
        self.fallback_handler = handler
        return handler

    def use(self, middleware: Middleware) -> None:
        self.middlewares.append(middleware)

    async def _dispatch(self, update: Update) -> None:
        context = Context(self.transport, self.state)
        current = self.state.get(update.chat_id)
        if update.command and update.command in self.commands:
            await self.commands[update.command](update, context)
        elif current and current in self.state_handlers:
            await self.state_handlers[current](update, context)
        elif self.fallback_handler:
            await self.fallback_handler(update, context)

    async def handle(self, update: Update) -> None:
        """Runs the middleware chain outermost-first, then the resolved handler."""
        async def call(index: int, upd: Update) -> None:
            if index >= len(self.middlewares):
                await self._dispatch(upd)
                return
            await self.middlewares[index](upd, lambda nxt: call(index + 1, nxt))

        await call(0, update)

    def run(self, updates: list[Update]) -> list[tuple[int, str]]:
        """Synchronous helper for scripts and tests: processes updates in order."""

        async def runner() -> None:
            for update in updates:
                await self.handle(update)

        asyncio.run(runner())
        sent = getattr(self.transport, "sent", [])
        return list(sent)


def logging_middleware(log: list[Update]) -> Middleware:
    async def middleware(update: Update, next_handler: Callable[[Update], Awaitable[None]]) -> None:
        log.append(update)
        await next_handler(update)

    return middleware


def rate_limit_middleware(max_per_chat: int = 5, replay: Callable[[Update], Awaitable[None]] | None = None) -> Middleware:
    seen: dict[int, int] = {}

    async def middleware(update: Update, next_handler: Callable[[Update], Awaitable[None]]) -> None:
        seen[update.chat_id] = seen.get(update.chat_id, 0) + 1
        if seen[update.chat_id] > max_per_chat:
            if replay:
                await replay(update)
            return
        await next_handler(update)

    return middleware
