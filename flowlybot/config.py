"""Typed, validated configuration.

Secrets (the bot token) come from the environment / .env — never the YAML.
Everything else lives in config.yaml so a non-coder can tune thresholds and
channel names without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(RuntimeError):
    pass


@dataclass
class SpamConfig:
    max_messages: int = 5
    interval_seconds: float = 7.0
    timeout_seconds: int = 300


@dataclass
class EscalationConfig:
    enabled: bool = True
    window_seconds: float = 600.0
    threshold: int = 3
    timeout_seconds: int = 3600


@dataclass
class AutomodConfig:
    enabled: bool = True
    exempt_roles: list[str] = field(default_factory=list)
    delete_scam: bool = True
    block_invites: bool = True
    allowed_invites: list[str] = field(default_factory=list)
    max_mentions: int = 5
    timeout_on_severe_seconds: int = 600
    spam: SpamConfig = field(default_factory=SpamConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)


@dataclass
class FaqConfig:
    prefix: str = "?"
    cooldown_seconds: float = 5.0
    ephemeral: bool = False


@dataclass
class ReleasesConfig:
    enabled: bool = True
    channel: str = "announcements"
    poll_minutes: float = 15.0
    pypi_package: str = "flowly-ai"
    github_repo: str = ""
    announce_github_releases: bool = False


@dataclass
class WelcomeConfig:
    enabled: bool = True
    assign_member_role: bool = True


@dataclass
class Config:
    token: str
    guild_id: int
    channels: dict[str, str]
    roles: dict[str, str]
    automod: AutomodConfig
    faq: FaqConfig
    releases: ReleasesConfig
    welcome: WelcomeConfig
    state_path: Path
    tags_path: Path
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        raw = yaml.safe_load(path.read_text()) or {}

        token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("DISCORD_BOT_TOKEN is not set (put it in .env)")

        guild_id = raw.get("guild_id")
        if not guild_id:
            raise ConfigError("guild_id is required in config.yaml")

        channels = raw.get("channels") or {}
        roles = raw.get("roles") or {}
        for required in ("announcements", "welcome", "mod_log"):
            if required not in channels:
                raise ConfigError(f"channels.{required} is required in config.yaml")

        am = raw.get("automod") or {}
        spam = SpamConfig(**(am.get("spam") or {}))
        esc = EscalationConfig(**(am.get("escalation") or {}))
        automod = AutomodConfig(
            **{k: v for k, v in am.items() if k not in ("spam", "escalation")},
            spam=spam,
            escalation=esc,
        )

        base = path.parent
        return cls(
            token=token,
            guild_id=int(guild_id),
            channels=channels,
            roles=roles,
            automod=automod,
            faq=FaqConfig(**(raw.get("faq") or {})),
            releases=ReleasesConfig(**(raw.get("releases") or {})),
            welcome=WelcomeConfig(**(raw.get("welcome") or {})),
            state_path=base / (raw.get("state_path") or "state/state.json"),
            tags_path=base / (raw.get("tags_path") or "flowlybot/data/tags.yaml"),
            raw=raw,
        )
