"""Rich GitHub activity feed — branded embeds for commits, PRs, and issues.

Replaces Discord's plain `/github` webhook with polled, color-coded embeds
(commits = cyan, PRs = green, issues = orange) that include the author, a
short message, and proper links. Polls the GitHub API on a schedule and tracks
the last-seen id per stream in state, seeding on first run so a restart never
floods #github. Releases stay in the Releases cog (→ #announcements).
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord.ext import commands, tasks

log = logging.getLogger("flowlybot.github_feed")
UA = {"User-Agent": "flowly-community-bot (+https://useflowlyapp.com)",
      "Accept": "application/vnd.github+json"}

CYAN = discord.Color.from_str("#00A6C8")
GREEN = discord.Color.from_str("#2ECC71")
ORANGE = discord.Color.from_str("#E67E22")
PURPLE = discord.Color.from_str("#9B59B6")


class GithubFeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("github_feed", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.repo = cfg.get("repo", "Nocetic/flowly")
        self.branch = cfg.get("branch", "main")
        self.channel = cfg.get("channel", "github")
        self.state = bot.state
        self._session: aiohttp.ClientSession | None = None
        if self.enabled:
            self.poll.change_interval(minutes=max(2.0, float(cfg.get("poll_minutes", 6))))
            self.poll.start()

    async def cog_unload(self) -> None:
        self.poll.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=UA)
        return self._session

    async def _get(self, path: str):
        try:
            s = await self._http()
            async with s.get(f"https://api.github.com{path}",
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("GET %s -> %s", path, r.status)
                    return None
                return await r.json()
        except Exception:
            log.warning("github fetch failed: %s", path, exc_info=True)
            return None

    def _channel(self):
        guild = self.bot.get_guild(self.bot.config.guild_id)
        return self.bot.resolve_channel(guild, self.channel) if guild else None

    async def _send(self, embed: discord.Embed) -> None:
        ch = self._channel()
        if ch is None:
            log.error("#%s not found", self.channel)
            return
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            log.warning("github feed post failed", exc_info=True)

    @tasks.loop(minutes=6)
    async def poll(self) -> None:
        await self._commits()
        await self._pulls()
        await self._issues()

    # --- commits ----------------------------------------------------------

    async def _commits(self) -> None:
        data = await self._get(f"/repos/{self.repo}/commits?sha={self.branch}&per_page=20")
        if not data or not isinstance(data, list):
            return
        key = "feed.commit"
        last = self.state.get(key)
        newest = data[0]["sha"]
        if last is None:
            self.state.set(key, newest)
            return
        new = []
        for c in data:
            if c["sha"] == last:
                break
            new.append(c)
        if not new:
            return
        self.state.set(key, newest)
        new.reverse()
        new = new[-10:]
        lines = []
        for c in new:
            sha = c["sha"][:7]
            url = c.get("html_url", "")
            msg = (c.get("commit", {}).get("message", "").splitlines() or [""])[0][:72]
            who = (c.get("author") or {}).get("login") or c.get("commit", {}).get("author", {}).get("name", "?")
            lines.append(f"[`{sha}`]({url}) {discord.utils.escape_markdown(msg)} — **{who}**")
        n = len(new)
        embed = discord.Embed(
            title=f"🔨 {n} new commit{'s' if n > 1 else ''} to `{self.branch}`",
            description="\n".join(lines), color=CYAN, timestamp=discord.utils.utcnow())
        first_author = (new[-1].get("author") or {})
        embed.set_author(name=self.repo, url=f"https://github.com/{self.repo}",
                         icon_url=first_author.get("avatar_url") or discord.utils.MISSING)
        embed.add_field(name="​",
                        value=f"[View changes](https://github.com/{self.repo}/compare/{last[:10]}...{newest[:10]})")
        await self._send(embed)

    # --- pull requests ----------------------------------------------------

    async def _pulls(self) -> None:
        data = await self._get(f"/repos/{self.repo}/pulls?state=all&sort=created&direction=desc&per_page=10")
        if not data or not isinstance(data, list):
            return
        key = "feed.pr"
        last = int(self.state.get(key) or 0)
        newest = max((p["number"] for p in data), default=0)
        if not self.state.get(key):
            self.state.set(key, newest)
            return
        fresh = sorted((p for p in data if p["number"] > last), key=lambda p: p["number"])
        for p in fresh[-5:]:
            merged = p.get("merged_at") is not None
            state_txt = "merged" if merged else p.get("state", "open")
            embed = discord.Embed(
                title=f"🔀 PR #{p['number']}: {p['title'][:200]}",
                url=p.get("html_url"),
                description=(p.get("body") or "").strip()[:300] or None,
                color=PURPLE if merged else GREEN, timestamp=discord.utils.utcnow())
            u = p.get("user", {})
            embed.set_author(name=f"{u.get('login','?')} · {state_txt}",
                             icon_url=u.get("avatar_url") or discord.utils.MISSING)
            await self._send(embed)
        if newest > last:
            self.state.set(key, newest)

    # --- issues -----------------------------------------------------------

    async def _issues(self) -> None:
        data = await self._get(f"/repos/{self.repo}/issues?state=all&sort=created&direction=desc&per_page=10")
        if not data or not isinstance(data, list):
            return
        issues = [i for i in data if "pull_request" not in i]  # exclude PRs
        key = "feed.issue"
        last = int(self.state.get(key) or 0)
        newest = max((i["number"] for i in issues), default=0)
        if not self.state.get(key):
            self.state.set(key, newest)
            return
        fresh = sorted((i for i in issues if i["number"] > last), key=lambda i: i["number"])
        for i in fresh[-5:]:
            embed = discord.Embed(
                title=f"🐛 Issue #{i['number']}: {i['title'][:200]}",
                url=i.get("html_url"),
                description=(i.get("body") or "").strip()[:300] or None,
                color=ORANGE, timestamp=discord.utils.utcnow())
            u = i.get("user", {})
            embed.set_author(name=f"{u.get('login','?')} · {i.get('state','open')}",
                             icon_url=u.get("avatar_url") or discord.utils.MISSING)
            await self._send(embed)
        if newest > last:
            self.state.set(key, newest)

    @poll.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GithubFeed(bot))
