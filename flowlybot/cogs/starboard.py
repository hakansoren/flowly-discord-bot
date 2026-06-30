"""Starboard — messages that reach N ⭐ get reposted to #best-of.

Uses raw reaction events (works for uncached messages). Persists the
source→board message mapping in state so reposts survive restarts and the
star count stays updated instead of duplicating.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger("flowlybot.starboard")


class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("starboard", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.channel = cfg.get("channel", "best-of")
        self.emoji = cfg.get("emoji", "⭐")
        self.threshold = int(cfg.get("threshold", 3))
        self.state = bot.state

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not self.enabled or str(payload.emoji) != self.emoji:
            return
        if payload.guild_id != self.bot.config.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        if channel is None or getattr(channel, "name", None) == self.channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if message.author.bot:
            return
        count = next((r.count for r in message.reactions if str(r.emoji) == self.emoji), 0)
        if count >= self.threshold:
            await self._post_or_update(guild, message, count)

    async def _post_or_update(self, guild, message, count) -> None:
        board = discord.utils.get(guild.text_channels, name=self.channel)
        if board is None:
            return
        embed = discord.Embed(description=message.content or "*(no text)*",
                              color=discord.Color.gold(), timestamp=message.created_at)
        embed.set_author(name=message.author.display_name,
                         icon_url=message.author.display_avatar.url)
        embed.add_field(name="Source", value=f"[jump to message]({message.jump_url}) · {message.channel.mention}")
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        content = f"{self.emoji} **{count}**"
        key = f"star.{message.id}"
        existing = self.state.get(key)
        if existing:
            try:
                board_msg = await board.fetch_message(existing)
                await board_msg.edit(content=content, embed=embed)
                return
            except discord.HTTPException:
                pass
        try:
            sent = await board.send(content=content, embed=embed)
            self.state.set(key, sent.id)
            log.info("starred message %s (%d)", message.id, count)
        except discord.HTTPException:
            log.warning("failed to post to starboard", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Starboard(bot))
