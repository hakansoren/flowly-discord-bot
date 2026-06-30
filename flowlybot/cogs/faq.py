"""FAQ / tag system.

`?install`, `?byok`, `?selfhost`, … post a curated answer so the team never
retypes the same thing. Content lives in flowlybot/data/tags.yaml (editable by
non-coders, hot-reloadable via /reloadtags). Also exposes a `/faq` slash
command with autocomplete and `?tags` to list everything.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import discord
import yaml
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("flowlybot.faq")
ACCENT = discord.Color.from_str("#00A6C8")  # Flowly cyan


def _load_tags(path: Path) -> dict[str, dict]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        log.error("tags file not found: %s", path)
        return {}
    except Exception:
        log.exception("failed to parse tags file")
        return {}
    out: dict[str, dict] = {}
    for key, val in data.items():
        key = str(key).lower()
        if isinstance(val, str):
            out[key] = {"title": key, "body": val}
        elif isinstance(val, dict) and val.get("body"):
            out[key] = {"title": val.get("title", key), "body": val["body"],
                        "link": val.get("link"), "aliases": val.get("aliases", [])}
    # expand aliases
    for key, val in list(out.items()):
        for alias in val.get("aliases", []) or []:
            out[str(alias).lower()] = val
    return out


class Faq(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config.faq
        self.path = bot.config.tags_path
        self.tags = _load_tags(self.path)
        self._cooldowns: dict[int, float] = {}
        log.info("loaded %d FAQ tags", len({id(v) for v in self.tags.values()}))

    # --- helpers ----------------------------------------------------------

    def _embed(self, entry: dict) -> discord.Embed:
        body = entry["body"]
        if entry.get("link"):
            body = f"{body}\n\n🔗 {entry['link']}"
        return discord.Embed(title=entry["title"], description=body, color=ACCENT)

    def _on_cooldown(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._cooldowns.get(user_id, 0.0)
        if now - last < self.cfg.cooldown_seconds:
            return True
        self._cooldowns[user_id] = now
        return False

    def _canonical_keys(self) -> list[str]:
        seen, keys = set(), []
        for k, v in self.tags.items():
            if id(v) not in seen:
                seen.add(id(v))
                keys.append(v.get("title", k))
        return sorted(keys)

    # --- prefix triggers --------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.guild.id != self.bot.config.guild_id:
            return
        content = message.content.strip()
        prefix = self.cfg.prefix
        if not content.startswith(prefix) or len(content) <= len(prefix):
            return
        token = content[len(prefix):].split()[0].lower()

        if token == "tags":
            if self._on_cooldown(message.author.id):
                return
            keys = self._canonical_keys()
            embed = discord.Embed(
                title="Available tags",
                description=" ".join(f"`{prefix}{k}`" for k in keys) or "— none —",
                color=ACCENT,
            )
            await message.channel.send(embed=embed)
            return

        entry = self.tags.get(token)
        if entry and not self._on_cooldown(message.author.id):
            await message.channel.send(embed=self._embed(entry))

    # --- slash command ----------------------------------------------------

    @app_commands.command(name="faq", description="Post a Flowly FAQ answer.")
    @app_commands.describe(topic="Which answer to post")
    async def faq_slash(self, interaction: discord.Interaction, topic: str) -> None:
        entry = self.tags.get(topic.lower())
        if not entry:
            await interaction.response.send_message(
                f"No tag `{topic}`. Try `{self.cfg.prefix}tags`.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self._embed(entry), ephemeral=self.cfg.ephemeral)

    @faq_slash.autocomplete("topic")
    async def _faq_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        keys = self._canonical_keys()
        return [app_commands.Choice(name=k, value=k) for k in keys if current in k.lower()][:25]

    @app_commands.command(name="reloadtags", description="Reload FAQ tags from disk (mods only).")
    async def reload_tags(self, interaction: discord.Interaction) -> None:
        perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
        if not perms or not (perms.manage_messages or perms.administrator):
            await interaction.response.send_message("You don't have permission.", ephemeral=True)
            return
        self.tags = _load_tags(self.path)
        n = len({id(v) for v in self.tags.values()})
        await interaction.response.send_message(f"Reloaded {n} tags.", ephemeral=True)
        log.info("tags reloaded by %s (%d)", interaction.user, n)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Faq(bot))
