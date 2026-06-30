"""Auto-link GitHub issue/PR references — `#123` → a clickable link.

Restricted to the dev/OSS channels (config) so casual `#5` mentions elsewhere
don't get linked. GitHub's /issues/N redirects to the PR if it's a PR.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ..detection import find_issue_refs

log = logging.getLogger("flowlybot.github_link")


class GithubLink(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("github", {})
        self.repo = cfg.get("repo", "Nocetic/flowly")
        self.channels = set(cfg.get("link_channels",
                                    ["dev-chat", "contributing", "feature-requests", "github"]))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not self.repo:
            return
        if message.guild.id != self.bot.config.guild_id:
            return
        if self.channels and getattr(message.channel, "name", None) not in self.channels:
            return
        refs = find_issue_refs(message.content)[:3]
        if not refs:
            return
        links = "\n".join(f"https://github.com/{self.repo}/issues/{n}" for n in refs)
        try:
            await message.reply(links, mention_author=False)
        except discord.HTTPException:
            log.warning("github link reply failed", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GithubLink(bot))
