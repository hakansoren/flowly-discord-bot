"""Feature-request voting — auto 👍/👎 + a discussion thread on each post."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger("flowlybot.voting")


class Voting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("engagement", {})
        self.channel = cfg.get("feature_request_channel", "feature-requests")
        self.up = cfg.get("vote_up", "👍")
        self.down = cfg.get("vote_down", "👎")
        self.auto_thread = bool(cfg.get("auto_thread", True))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.guild.id != self.bot.config.guild_id:
            return
        if getattr(message.channel, "name", None) != self.channel:
            return
        if message.content.startswith(self.bot.config.faq.prefix):
            return
        try:
            await message.add_reaction(self.up)
            await message.add_reaction(self.down)
            if self.auto_thread and message.thread is None:
                name = (message.content.strip().splitlines()[0] if message.content.strip() else "feature request")[:90]
                await message.create_thread(name=name, auto_archive_duration=10080)
        except discord.HTTPException:
            log.warning("voting failed on %s", message.id, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Voting(bot))
