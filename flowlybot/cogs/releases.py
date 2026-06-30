"""Automatic release announcements.

Polls PyPI (the `flowly-ai` package) and, optionally, the GitHub repo's latest
release. On the very first run it *seeds* the current versions without
announcing, so a reboot never spams #announcements. After that, a newer PyPI
version or a freshly-published GitHub release posts a tidy embed.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands, tasks

from ..detection import is_newer

log = logging.getLogger("flowlybot.releases")
ACCENT = discord.Color.from_str("#00A6C8")
UA = {"User-Agent": "flowly-community-bot (+https://useflowlyapp.com)"}

PYPI_KEY = "release.pypi"
GITHUB_KEY = "release.github"


class Releases(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config.releases
        self.state = bot.state
        self._session: aiohttp.ClientSession | None = None
        if self.cfg.enabled:
            self.poll.change_interval(minutes=max(1.0, self.cfg.poll_minutes))
            self.poll.start()

    async def cog_unload(self) -> None:
        self.poll.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=UA)
        return self._session

    async def _get_json(self, url: str) -> dict | None:
        try:
            sess = await self._http()
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("GET %s -> %s", url, r.status)
                    return None
                return await r.json()
        except Exception:
            log.warning("fetch failed: %s", url, exc_info=True)
            return None

    def _channel(self) -> discord.abc.Messageable | None:
        guild = self.bot.get_guild(self.bot.config.guild_id)
        if guild is None:
            return None
        return self.bot.resolve_channel(guild, self.cfg.channel)

    async def _announce(self, *, title: str, version: str, url: str | None, source: str) -> None:
        ch = self._channel()
        if ch is None:
            log.error("announcements channel '%s' not found", self.cfg.channel)
            return
        embed = discord.Embed(title=title, color=ACCENT, timestamp=discord.utils.utcnow())
        embed.description = f"**{version}** is out."
        if url:
            embed.description += f"\n\n🔗 {url}"
        embed.set_footer(text=f"via {source}")
        try:
            await ch.send(embed=embed)
            log.info("announced %s %s", source, version)
        except discord.HTTPException:
            log.exception("failed to post release announcement")

    @tasks.loop(minutes=15)
    async def poll(self) -> None:
        await self._check_pypi()
        if self.cfg.announce_github_releases and self.cfg.github_repo:
            await self._check_github()

    async def _check_pypi(self) -> None:
        data = await self._get_json(f"https://pypi.org/pypi/{self.cfg.pypi_package}/json")
        version = (data or {}).get("info", {}).get("version")
        if not version:
            return
        prev = self.state.get(PYPI_KEY)
        if prev is None:
            self.state.set(PYPI_KEY, version)  # seed, no announce
            log.info("seeded PyPI version %s", version)
            return
        if is_newer(prev, version):
            self.state.set(PYPI_KEY, version)
            await self._announce(
                title="🚀 New Flowly release",
                version=f"v{version}",
                url=f"https://pypi.org/project/{self.cfg.pypi_package}/{version}/",
                source="PyPI",
            )

    async def _check_github(self) -> None:
        data = await self._get_json(f"https://api.github.com/repos/{self.cfg.github_repo}/releases/latest")
        if not data:
            return
        tag = data.get("tag_name")
        if not tag:
            return
        prev = self.state.get(GITHUB_KEY)
        if prev is None:
            self.state.set(GITHUB_KEY, tag)  # seed
            log.info("seeded GitHub release %s", tag)
            return
        if tag != prev:
            self.state.set(GITHUB_KEY, tag)
            await self._announce(
                title="🚀 New Flowly release",
                version=data.get("name") or tag,
                url=data.get("html_url"),
                source="GitHub",
            )

    @poll.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Releases(bot))
