#!/usr/bin/env python3
"""Flowly community Discord bot — entrypoint.

Run: python bot.py   (after copying .env.example -> .env and filling the token)
Config lives in config.yaml; secrets in .env.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from flowlybot.config import Config, ConfigError
from flowlybot.logging_setup import setup_logging
from flowlybot.state import State

log = logging.getLogger("flowlybot")

COGS = (
    "flowlybot.cogs.automod",
    "flowlybot.cogs.faq",
    "flowlybot.cogs.releases",
    "flowlybot.cogs.welcome",
    "flowlybot.cogs.voting",
    "flowlybot.cogs.starboard",
    "flowlybot.cogs.github_link",
    "flowlybot.cogs.stats",
    "flowlybot.cogs.docs_search",
    "flowlybot.cogs.ops",
)


class FlowlyBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True   # privileged — enable in the Dev Portal
        intents.members = True           # privileged — enable in the Dev Portal
        intents.guilds = True
        super().__init__(command_prefix=config.faq.prefix, intents=intents, help_command=None)
        self.config = config
        self.state = State(config.state_path)

    # name-based resolution so renaming an ID never breaks config
    def resolve_channel(self, guild: discord.Guild, name: str | None):
        if not name:
            return None
        return discord.utils.get(guild.channels, name=name)

    def resolve_role(self, guild: discord.Guild, name: str | None):
        if not name:
            return None
        return discord.utils.get(guild.roles, name=name)

    async def setup_hook(self) -> None:
        for ext in COGS:
            try:
                await self.load_extension(ext)
                log.info("loaded %s", ext)
            except Exception:
                log.exception("failed to load %s", ext)
        guild = discord.Object(id=self.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("synced %d slash command(s) to guild %s", len(synced), self.config.guild_id)

    async def on_ready(self) -> None:
        log.info("logged in as %s (%s)", self.user, getattr(self.user, "id", "?"))
        self._validate_targets()

    async def on_command_error(self, ctx, error) -> None:
        # We use no prefix commands (tags/FAQ are on_message listeners), so the
        # command processor raises CommandNotFound on every `?tag`. Swallow it;
        # log anything genuinely unexpected.
        if isinstance(error, commands.CommandNotFound):
            return
        log.error("command error: %s", error, exc_info=error)

    def _validate_targets(self) -> None:
        guild = self.get_guild(self.config.guild_id)
        if guild is None:
            log.error("bot is not in configured guild %s — invite it first", self.config.guild_id)
            return
        for key, name in self.config.channels.items():
            if self.resolve_channel(guild, name) is None:
                log.warning("configured channel '%s' (%s) not found in guild", name, key)
        member_role = self.config.roles.get("member")
        if member_role and self.resolve_role(guild, member_role) is None:
            log.warning("configured member role '%s' not found", member_role)


async def _amain() -> int:
    load_dotenv()
    config_path = os.environ.get("FLOWLY_BOT_CONFIG", "config.yaml")
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(log_level)

    try:
        config = Config.load(config_path)
    except ConfigError as e:
        log.error("config error: %s", e)
        return 2

    bot = FlowlyBot(config)
    try:
        await bot.start(config.token)
    except discord.LoginFailure:
        log.error("login failed — check DISCORD_BOT_TOKEN")
        return 3
    except discord.PrivilegedIntentsRequired:
        log.error("enable the Message Content + Server Members intents in the Developer Portal")
        return 4
    finally:
        if not bot.is_closed():
            await bot.close()
    return 0


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
