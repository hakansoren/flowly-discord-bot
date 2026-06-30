"""Anti-scam + lightweight auto-mod.

Design principles (the "be careful" bar):
- Never act on bots, the bot itself, or anyone who can already moderate
  (manage_messages / administrator) or sits in an exempt role.
- Default actions are conservative: delete the offending message and log it.
  A timeout is only applied for *severe* hits (phishing / scam / mass-mention)
  or for repeat offenders — and the bot NEVER auto-bans. Bans stay human.
- Every action is mirrored to the mod-log channel with full context so a
  human can review and reverse it.
- All thresholds are config-driven; nothing is hard-coded.
"""

from __future__ import annotations

import collections
import datetime as dt
import logging
import time

import discord
from discord.ext import commands

from ..detection import Violation, analyze

log = logging.getLogger("flowlybot.automod")


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config.automod
        # user_id -> recent message timestamps (spam window)
        self._msgs: dict[int, collections.deque] = collections.defaultdict(collections.deque)
        # user_id -> recent infraction timestamps (escalation window)
        self._infractions: dict[int, collections.deque] = collections.defaultdict(collections.deque)

    # --- helpers ----------------------------------------------------------

    def _exempt(self, member: discord.Member) -> bool:
        perms = member.guild_permissions
        if perms.administrator or perms.manage_messages or perms.kick_members:
            return True
        return bool({r.name for r in member.roles} & set(self.cfg.exempt_roles))

    async def _modlog(self, guild: discord.Guild, *, title: str, color: discord.Color,
                      member: discord.abc.User, action: str, reasons: list[str],
                      channel: discord.abc.GuildChannel | None, content: str) -> None:
        ch = self.bot.resolve_channel(guild, self.bot.config.channels.get("mod_log"))
        if ch is None:
            return
        embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{member.mention} (`{member}` · {member.id})", inline=False)
        embed.add_field(name="Action", value=action, inline=True)
        if channel is not None:
            embed.add_field(name="Channel", value=getattr(channel, "mention", str(channel)), inline=True)
        embed.add_field(name="Reasons", value=", ".join(reasons) or "—", inline=False)
        if content:
            embed.add_field(name="Message", value=discord.utils.escape_markdown(content[:900]) or "—", inline=False)
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            log.exception("failed to write mod-log")

    def _record_infraction(self, user_id: int) -> int:
        now = time.monotonic()
        dq = self._infractions[user_id]
        dq.append(now)
        window = self.cfg.escalation.window_seconds
        while dq and now - dq[0] > window:
            dq.popleft()
        return len(dq)

    async def _timeout(self, member: discord.Member, seconds: int, reason: str) -> bool:
        try:
            await member.timeout(dt.timedelta(seconds=seconds), reason=reason)
            return True
        except (discord.Forbidden, discord.HTTPException):
            log.warning("timeout failed for %s", member.id, exc_info=True)
            return False

    # --- spam -------------------------------------------------------------

    def _is_spam(self, user_id: int) -> bool:
        s = self.cfg.spam
        now = time.monotonic()
        dq = self._msgs[user_id]
        dq.append(now)
        while dq and now - dq[0] > s.interval_seconds:
            dq.popleft()
        return len(dq) > s.max_messages

    # --- main listener ----------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.cfg.enabled:
            return
        if message.author.bot or message.guild is None:
            return
        if message.guild.id != self.bot.config.guild_id:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            member = message.guild.get_member(member.id) or member
        if isinstance(member, discord.Member) and self._exempt(member):
            return

        violations: list[Violation] = analyze(
            message.content,
            mention_count=len(message.mentions),
            mention_everyone=message.mention_everyone,
            max_mentions=self.cfg.max_mentions,
            allowed_invites=tuple(self.cfg.allowed_invites),
        )

        # Filter out classes the operator disabled.
        if not self.cfg.delete_scam:
            violations = [v for v in violations if v.kind not in ("phishing", "scam_keyword")]
        if not self.cfg.block_invites:
            violations = [v for v in violations if v.kind != "invite"]

        if violations:
            await self._handle_content_violation(message, member, violations)
            return

        # Spam is separate from content rules.
        if self._is_spam(member.id):
            await self._handle_spam(message, member)

    async def _handle_content_violation(self, message, member, violations) -> None:
        reasons = [f"{v.kind}:{v.detail}" for v in violations]
        deleted = False
        try:
            await message.delete()
            deleted = True
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            log.warning("could not delete flagged message %s", message.id, exc_info=True)

        action = "deleted"
        severe = any(v.severe for v in violations)
        if isinstance(member, discord.Member) and severe:
            count = self._record_infraction(member.id)
            esc = self.cfg.escalation
            secs = self.cfg.timeout_on_severe_seconds
            if esc.enabled and count >= esc.threshold:
                secs = max(secs, esc.timeout_seconds)
                action = "deleted + timeout (repeat offender)"
            else:
                action = "deleted + timeout"
            if await self._timeout(member, secs, reason="; ".join(reasons)[:400]):
                action += f" {secs}s"
        elif not deleted:
            action = "flagged (delete failed)"

        log.info("automod %s on %s: %s", action, member, reasons)
        await self._modlog(
            message.guild, title="🛡️ Auto-mod action", color=discord.Color.red(),
            member=member, action=action, reasons=reasons,
            channel=message.channel, content=message.content,
        )

    async def _handle_spam(self, message, member) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        action = "spam: deleted"
        if isinstance(member, discord.Member):
            secs = self.cfg.spam.timeout_seconds
            if await self._timeout(member, secs, reason="message spam"):
                action = f"spam: deleted + timeout {secs}s"
        log.info("automod %s on %s", action, member)
        await self._modlog(
            message.guild, title="🛡️ Auto-mod: spam", color=discord.Color.orange(),
            member=member, action=action, reasons=["rate-limit exceeded"],
            channel=message.channel, content=message.content,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
