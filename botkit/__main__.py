"""Demo: the framework running against an in-memory transport - no token needed."""
from __future__ import annotations

from .core import Bot, Context, MemoryTransport, Update


def demo() -> None:
    bot = Bot(transport=MemoryTransport())

    @bot.command("start")
    async def start(update: Update, ctx: Context) -> None:
        ctx.state.set(update.chat_id, "awaiting_name")
        await ctx.reply(update, "What is your name?")

    @bot.on_state("awaiting_name")
    async def name(update: Update, ctx: Context) -> None:
        ctx.state.clear(update.chat_id)
        await ctx.reply(update, f"Hello {update.text}")

    @bot.fallback
    async def fallback(update: Update, ctx: Context) -> None:
        await ctx.reply(update, "Try /start")

    for chat_id, text in bot.run([Update(1, "/start"), Update(1, "Ada"), Update(1, "hi")]):
        print(f"-> {chat_id}: {text}")


if __name__ == "__main__":
    demo()
