"""Live documentation index — keyword search over the real Flowly docs.

Pulls the docs straight from the public repo (`content/docs/**.md`) via the
GitHub tree API + raw.githubusercontent.com, parses frontmatter, and ranks
pages by term overlap. No AI, no per-query network — the index refreshes on a
schedule and `/search` runs against the in-memory copy.

parse_doc / path_to_url / rank are pure and unit-tested; refresh is the only
async/network part.
"""

from __future__ import annotations

import asyncio
import logging
import re

import yaml

log = logging.getLogger("flowlybot.docs")

_MD_NOISE = re.compile(r"[#>*`\[\]()_|]")


def parse_doc(path: str, raw: str) -> dict:
    title, desc, body = None, "", raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                title = fm.get("title")
                desc = fm.get("description", "") or ""
            except Exception:
                pass
            body = parts[2]
    if not title:
        title = path.rsplit("/", 1)[-1][:-3].replace("-", " ").title()
    text = _MD_NOISE.sub(" ", body)
    return {"path": path, "title": str(title), "description": str(desc), "text": text}


def path_to_url(path: str, docs_path: str, site_base: str) -> str:
    rel = path[len(docs_path):] if path.startswith(docs_path) else path
    if rel.endswith(".md"):
        rel = rel[:-3]
    if rel.endswith("/index") or rel == "index":
        rel = rel[: -len("index")].rstrip("/")
    return f"{site_base.rstrip('/')}/{rel}".rstrip("/")


def rank(entries: list[dict], query: str, limit: int = 3) -> list[dict]:
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
    if not terms:
        return []
    scored = []
    for e in entries:
        fname = e["path"].rsplit("/", 1)[-1].lower()
        title = e["title"].lower()
        desc = e["description"].lower()
        text = e["text"].lower()
        score = 0.0
        for t in terms:
            if t in fname:
                score += 5
            if t in title:
                score += 4
            if t in desc:
                score += 2
            score += min(text.count(t), 6) * 0.5
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


class DocsIndex:
    def __init__(self, repo: str, branch: str, docs_path: str, site_base: str):
        self.repo = repo
        self.branch = branch
        self.docs_path = docs_path
        self.site_base = site_base
        self.entries: list[dict] = []

    def search(self, query: str, limit: int = 3) -> list[dict]:
        return rank(self.entries, query, limit)

    async def refresh(self, session) -> int:
        """Fetch + index all docs. Returns the entry count (0 = unchanged on failure)."""
        tree_url = f"https://api.github.com/repos/{self.repo}/git/trees/{self.branch}?recursive=1"
        try:
            async with session.get(tree_url, timeout=_timeout(20)) as r:
                if r.status != 200:
                    log.warning("docs tree fetch -> %s", r.status)
                    return 0
                tree = await r.json()
        except Exception:
            log.warning("docs tree fetch failed", exc_info=True)
            return 0

        paths = [t["path"] for t in tree.get("tree", [])
                 if t["path"].startswith(self.docs_path) and t["path"].endswith(".md")]
        sem = asyncio.Semaphore(8)

        async def fetch(path: str) -> dict | None:
            url = f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{path}"
            async with sem:
                try:
                    async with session.get(url, timeout=_timeout(15)) as r:
                        if r.status != 200:
                            return None
                        raw = await r.text()
                except Exception:
                    return None
            e = parse_doc(path, raw)
            e["url"] = path_to_url(path, self.docs_path, self.site_base)
            return e

        results = await asyncio.gather(*(fetch(p) for p in paths))
        entries = [e for e in results if e]
        if entries:
            self.entries = entries
            log.info("docs index refreshed: %d pages", len(entries))
        return len(entries)


def _timeout(total: float):
    import aiohttp
    return aiohttp.ClientTimeout(total=total)
