"""Pure, dependency-free detection helpers.

Kept free of any Discord imports so the heuristics can be unit-tested in
isolation (see tests/test_logic.py). The cogs feed plain strings/counts in
and act on the returned violations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# discord.gg/abc, discord.com/invite/abc, discordapp.com/invite/abc, discord.io/abc …
INVITE_RE = re.compile(
    r"\b(?:discord(?:app)?\.com/invite|discord\.(?:gg|io|me|li))/([A-Za-z0-9-]+)", re.I
)
# Grab the host of any http(s) URL.
URL_RE = re.compile(r"https?://([^\s/]+)", re.I)

# Substrings that show up in Discord/Steam/crypto phishing look-alike hosts.
PHISH_DOMAIN_HINTS = (
    "dlscord", "discrod", "discrod", "disccord", "discord-nitro", "discordnitro",
    "discordgift", "discord-gift", "nitro-discord", "discord-airdrop",
    "discordapp.ru", "steamcommunity.ru", "steam-community", "steampowered.ru",
    "discord-give", "discrodnitro", "free-nitro",
)
# Lure phrases — only treated as a violation when a link is ALSO present, so a
# plain "is nitro free?" question never trips the filter.
SCAM_PHRASES = (
    "free nitro", "nitro free", "free discord nitro", "discord nitro free",
    "steam gift", "free gift", "airdrop", "claim your", "free robux",
    "1 month nitro", "3 month nitro", "get nitro now", "@everyone free",
)


@dataclass(frozen=True)
class Violation:
    kind: str     # "phishing" | "scam_keyword" | "invite" | "mass_mention"
    detail: str

    @property
    def severe(self) -> bool:
        # Severe → worth a timeout, not just a delete.
        return self.kind in ("phishing", "scam_keyword", "mass_mention")


def find_invites(content: str) -> list[str]:
    return INVITE_RE.findall(content or "")


def find_domains(content: str) -> list[str]:
    return [d.lower() for d in URL_RE.findall(content or "")]


def analyze(
    content: str,
    *,
    mention_count: int = 0,
    mention_everyone: bool = False,
    max_mentions: int = 5,
    allowed_invites: tuple[str, ...] = (),
) -> list[Violation]:
    """Return every rule a message trips. Empty list == clean."""
    content = content or ""
    low = content.lower()
    domains = find_domains(content)
    invites = find_invites(content)
    out: list[Violation] = []

    for d in domains:
        if any(h in d for h in PHISH_DOMAIN_HINTS):
            out.append(Violation("phishing", d))
            break

    if (domains or invites) and any(p in low for p in SCAM_PHRASES):
        phrase = next(p for p in SCAM_PHRASES if p in low)
        out.append(Violation("scam_keyword", phrase))

    allow = {a.lower() for a in allowed_invites}
    bad = [i for i in invites if i.lower() not in allow]
    if bad:
        out.append(Violation("invite", bad[0]))

    if mention_everyone or mention_count > max_mentions:
        out.append(Violation("mass_mention", f"mentions={mention_count} everyone={mention_everyone}"))

    return out


# --- release version comparison ------------------------------------------

ISSUE_RE = re.compile(r"(?<![\w/#])#(\d{1,6})\b")


def find_issue_refs(content: str) -> list[str]:
    """Extract GitHub issue/PR refs like `#123` (not part of a word/url)."""
    seen, out = set(), []
    for n in ISSUE_RE.findall(content or ""):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def version_tuple(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(old: str | None, new: str | None) -> bool:
    """True if `new` should be announced over `old` (strictly greater)."""
    if not new:
        return False
    if not old:
        return True
    try:
        return version_tuple(new) > version_tuple(old)
    except Exception:
        return new != old
