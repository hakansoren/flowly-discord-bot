"""Welcome new members + assign the base Member role."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger("flowlybot.welcome")
ACCENT = discord.Color.from_str("#00A6C8")


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config.welcome

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self.cfg.enabled:
            return
        if member.guild.id != self.bot.config.guild_id:
            return
        if member.bot:
            return

        if self.cfg.assign_member_role:
            await self._assign_member_role(member)
        await self._greet(member)

    async def _assign_member_role(self, member: discord.Member) -> None:
        role_name = self.bot.config.roles.get("member")
        if not role_name:
            return
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role is None:
            log.warning("member role '%s' not found", role_name)
            return
        try:
            await member.add_roles(role, reason="auto Member role on join")
            log.info("assigned %s to %s", role_name, member)
        except (discord.Forbidden, discord.HTTPException):
            log.warning("could not assign member role to %s", member.id, exc_info=True)

    async def _greet(self, member: discord.Member) -> None:
        ch = self.bot.resolve_channel(member.guild, self.bot.config.channels.get("welcome"))
        if ch is None:
            return
        rules = self.bot.resolve_channel(member.guild, self.bot.config.channels.get("rules"))
        roles = self.bot.resolve_channel(member.guild, self.bot.config.channels.get("roles"))
        rules_m = rules.mention if rules else "#rules"
        roles_m = roles.mention if roles else "#roles"

        embed = discord.Embed(
            title=f"Welcome, {member.display_name} 👋",
            description=(
                "Glad you're here. Flowly is the personal AI agent you own — "
                "your machine, your keys, a memory of your world.\n\n"
                f"• Read the {rules_m}\n"
                f"• Pick your platform in {roles_m}\n"
                "• Say hi and tell us what you're building."
            ),
            color=ACCENT,
        )
        try:
            await ch.send(content=member.mention, embed=embed)
        except discord.HTTPException:
            log.exception("failed to send welcome message")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
