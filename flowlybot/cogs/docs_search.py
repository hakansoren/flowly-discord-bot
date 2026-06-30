"""`/search <query>` — keyword search over the FAQ/docs tags. No AI, no network.

Ranks the curated FAQ entries by term overlap with the query and returns the
best matches (with their doc links), so members can find an answer without
knowing the exact tag name.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("flowlybot.docs_search")
ACCENT = discord.Color.from_str("#00A6C8")
DOCS_URL = "https://useflowlyapp.com/en/docs"


class DocsSearch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _faq_tags(self) -> dict:
        faq = self.bot.get_cog("Faq")
        return getattr(faq, "tags", {}) if faq else {}

    @app_commands.command(name="search", description="Search the Flowly docs/FAQ by keyword.")
    @app_commands.describe(query="What are you looking for?")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        terms = [t for t in query.lower().split() if len(t) > 1]
        tags = self._faq_tags()
        scored, seen = [], set()
        for key, entry in tags.items():
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            hay = f"{key} {entry.get('title','')} {entry.get('body','')}".lower()
            score = sum(hay.count(t) for t in terms) + sum(2 for t in terms if t in key)
            if score:
                scored.append((score, key, entry))
        scored.sort(key=lambda x: -x[0])
        top = scored[:3]
        if not top:
            await interaction.response.send_message(
                f"No match for **{query}**. Browse the docs: {DOCS_URL}", ephemeral=True)
            return
        embed = discord.Embed(title=f"Results for “{query}”", color=ACCENT)
        for _, key, entry in top:
            body = entry.get("body", "").strip().splitlines()[0][:120]
            link = entry.get("link")
            val = body + (f"\n{link}" if link else "")
            embed.add_field(name=entry.get("title", key), value=val or "—", inline=False)
        embed.set_footer(text="Full docs: useflowlyapp.com/en/docs")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DocsSearch(bot))
