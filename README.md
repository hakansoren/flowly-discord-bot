# Flowly Community Bot

A small, dependency-light 24/7 Discord bot for the Flowly community. No AI, no
LLM credits — purely deterministic utility:

| Feature | What it does |
|---|---|
| 🛡️ **Auto-mod** | Deletes phishing/scam links, blocks unsolicited invites, catches mass-mentions and spam. Times out severe/repeat offenders. Mods are auto-exempt. Never auto-bans. Everything logged to a mod-log channel. |
| 🆘 **FAQ / tags** | `?install`, `?byok`, `?selfhost`, … post curated answers. Also `/faq` (autocomplete) and `?tags`. Content in `flowlybot/data/tags.yaml`, hot-reloadable with `/reloadtags`. |
| 🚀 **Release announcer** | Polls PyPI (`flowly-ai`) + GitHub releases and posts new versions to `#announcements`. Seeds on first run so reboots never spam. |
| 👋 **Welcome** | Greets new members and assigns the `Member` role. |

## Architecture

```
bot.py                     entrypoint (FlowlyBot, cog loading, slash sync)
flowlybot/
  config.py                typed + validated config (YAML + .env)
  detection.py             pure heuristics (scam/invite/version) — unit-tested
  state.py                 atomic JSON state (last-announced versions)
  logging_setup.py         console + rotating file logs
  cogs/
    automod.py  faq.py  releases.py  welcome.py
  data/tags.yaml           FAQ content
deploy/flowly-bot.service  systemd unit
tests/test_logic.py        pytest (no Discord/network needed)
```

Channels and roles are referenced **by name** in `config.yaml`, so renaming or
re-creating them never breaks the bot.

## Setup

1. **Bot application** — in the [Developer Portal](https://discord.com/developers):
   - Bot tab → **enable `MESSAGE CONTENT INTENT` and `SERVER MEMBERS INTENT`** (required).
   - Copy the bot token.
   - Invite it with **Manage Roles, Manage Messages, Moderate Members** (or Administrator).
   - Its role must sit **above** the `Member` role in the hierarchy.

2. **Install**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env          # paste your token into DISCORD_BOT_TOKEN
   cp config.example.yaml config.yaml   # set guild_id + names
   ```

3. **Run**
   ```bash
   python bot.py
   ```

## Deploy (VPS, systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin flowlybot
sudo mkdir -p /opt/flowly-discord-bot && sudo chown flowlybot: /opt/flowly-discord-bot
# copy the project there, create .venv, pip install -r requirements.txt
sudo cp deploy/flowly-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now flowly-bot
journalctl -u flowly-bot -f
```

## Tests

```bash
pip install pytest
pytest -q
```

## Notes

- **Secrets** live only in `.env` (gitignored). `config.yaml` and `state/` are
  gitignored too.
- Auto-mod defaults are conservative and fully tunable in `config.yaml`. Start
  permissive, tighten as you see real traffic.
- Editing FAQ answers is just editing `flowlybot/data/tags.yaml` → `/reloadtags`.
