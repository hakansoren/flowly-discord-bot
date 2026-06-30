"""`/search <query>` — live keyword search over the real Flowly docs.

Indexes the published docs from the public repo (refreshed on startup + every
few hours) and ranks pages by term overlap. Falls back to the curated FAQ tags
when the index isn't ready or a query has no doc hit. No AI, no per-query
network.
"""

from __future__ import annotations

import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..docs_index import DocsIndex

log = logging.getLogger("flowlybot.docs_search")
ACCENT = discord.Color.from_str("#00A6C8")
DOCS_HOME = "https://useflowlyapp.com/en/docs"


class DocsSearch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        cfg = bot.config.raw.get("docs", {})
        self.index = DocsIndex(
            repo=cfg.get("repo", "Nocetic/flowly"),
            branch=cfg.get("branch", "main"),
            docs_path=cfg.get("docs_path", "content/docs/"),
            site_base=cfg.get("site_base", DOCS_HOME),
        )
        self._session: aiohttp.ClientSession | None = None
        self.refresh.change_interval(hours=max(1.0, float(cfg.get("refresh_hours", 6))))
        self.refresh.start()

    async def cog_unload(self) -> None:
        self.refresh.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    @tasks.loop(hours=6)
    async def refresh(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "flowly-community-bot (+https://useflowlyapp.com)"})
        await self.index.refresh(self._session)

    @refresh.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    def _faq_fallback(self, query: str) -> list[dict]:
        faq = self.bot.get_cog("Faq")
        tags = getattr(faq, "tags", {}) if faq else {}
        terms = [t for t in query.lower().split() if len(t) > 1]
        out, seen = [], set()
        for key, entry in tags.items():
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            hay = f"{key} {entry.get('title','')} {entry.get('body','')}".lower()
            if any(t in hay for t in terms):
                out.append({"title": entry.get("title", key),
                            "description": entry.get("body", "").strip().splitlines()[0][:140],
                            "url": entry.get("link")})
        return out[:3]

    @app_commands.command(name="search", description="Search the Flowly docs by keyword.")
    @app_commands.describe(query="What are you looking for?")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        results = self.index.search(query, limit=3)
        source = "docs"
        if not results:
            results = self._faq_fallback(query)
            source = "faq"
        if not results:
            await interaction.response.send_message(
                f"No match for **{query}**. Browse the docs: {DOCS_HOME}", ephemeral=True)
            return

        embed = discord.Embed(title=f"Results for “{query}”", color=ACCENT)
        for e in results:
            desc = (e.get("description") or "").strip()
            url = e.get("url")
            val = (desc[:160] or "—") + (f"\n🔗 {url}" if url else "")
            embed.add_field(name=e["title"], value=val, inline=False)
        embed.set_footer(text=f"{len(self.index.entries)} docs pages · useflowlyapp.com/en/docs")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DocsSearch(bot))
