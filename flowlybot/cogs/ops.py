"""Ops visibility — posts a one-line notice to the mod-log on (re)start.

systemd restarts the bot on crash, but silently. This makes every cold start
visible in #moderator-only, so unexpected restarts are noticeable.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

import flowlybot

log = logging.getLogger("flowlybot.ops")


class Ops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._announced = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._announced:
            return
        if not self.bot.config.raw.get("ops", {}).get("startup_notice", True):
            return
        self._announced = True
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if guild is None:
            return
        ch = self.bot.resolve_channel(guild, self.bot.config.channels.get("mod_log"))
        if ch is None:
            return
        try:
            await ch.send(f"✅ Flowly bot online — v{flowlybot.__version__}")
        except discord.HTTPException:
            log.warning("startup notice failed", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ops(bot))
