"""Live member-count channel — updates a `👥 Members: N` voice channel name.

Channel renames are heavily rate-limited by Discord (~2 per 10 min), so the
loop runs on a ≥5-minute cadence and only edits when the count changed.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

log = logging.getLogger("flowlybot.stats")


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("stats", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.prefix = cfg.get("member_channel_prefix", "👥 Members")
        minutes = max(5.0, float(cfg.get("update_minutes", 10)))
        if self.enabled:
            self.update.change_interval(minutes=minutes)
            self.update.start()

    async def cog_unload(self) -> None:
        self.update.cancel()

    @tasks.loop(minutes=10)
    async def update(self) -> None:
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if guild is None:
            return
        ch = discord.utils.find(lambda c: c.name.startswith(self.prefix), guild.channels)
        if ch is None:
            return
        count = guild.member_count
        new_name = f"{self.prefix}: {count}"
        if ch.name != new_name:
            try:
                await ch.edit(name=new_name, reason="member-count stat")
                log.info("member count -> %s", count)
            except discord.HTTPException:
                log.warning("member-count rename failed (rate limit?)", exc_info=True)

    @update.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
