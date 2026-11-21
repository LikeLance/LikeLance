#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh assets/stats-{light,dark}.svg from the GitHub API.

Stdlib only. Runs in Actions with the default GITHUB_TOKEN; no third-party
image services, so nothing here can rate-limit or go dark on us.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

LOGIN = os.environ.get("GH_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "LikeLance"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
OUT = pathlib.Path(__file__).resolve().parent.parent / "assets"

SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "'Helvetica Neue', Arial, 'Noto Sans', sans-serif")
MONO = ("ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, "
        "'Liberation Mono', 'Courier New', monospace")

PALETTES = {
    "light": dict(bg="#ffffff", ink="#0b0b0f", muted="#71717a", line="#e4e4e9", accent="#ff4d00"),
    "dark": dict(bg="#0d1117", ink="#e6edf3", muted="#8b949e", line="#21262d", accent="#ff6a2b"),
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes { stargazerCount primaryLanguage { name } }
    }
    contributionsCollection {
      contributionCalendar { totalContributions }
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      commitContributionsByRepository(maxRepositories: 15) {
        contributions
        repository { primaryLanguage { name } }
      }
    }
  }
}
"""


def gh(path: str, payload: dict | None = None) -> dict:
    url = "https://api.github.com" + path
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{LOGIN}-profile-stats")
    if TOKEN:
        req.add_header("Authorization", f"bearer {TOKEN}")
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(n)


def collect() -> list[tuple[str, str]]:
    data = gh("/graphql", {"query": QUERY, "variables": {"login": LOGIN}})
    if "errors" in data:
        raise RuntimeError(f"GraphQL: {data['errors']}")
    u = data["data"]["user"]

    repos = u["repositories"]
    stars = sum(int(r["stargazerCount"]) for r in repos["nodes"] or [])
    cc = u["contributionsCollection"]

    langs: dict[str, int] = {}
    for row in cc["commitContributionsByRepository"] or []:
        lang = ((row.get("repository") or {}).get("primaryLanguage") or {}).get("name")
        if lang:
            langs[lang] = langs.get(lang, 0) + int(row["contributions"])
    top = max(langs, key=langs.get) if langs else "—"

    return [
        (fmt(int(cc["contributionCalendar"]["totalContributions"])), "CONTRIBUTIONS / 365D"),
        (fmt(int(repos["totalCount"])), "PUBLIC REPOS"),
        (fmt(stars), "STARS EARNED"),
        (fmt(int(cc["totalCommitContributions"])), "COMMITS / 365D"),
        (fmt(int(u["followers"]["totalCount"])), "FOLLOWERS"),
        (top.upper(), "TOP LANGUAGE"),
    ]


def svg(p: dict, cells: list[tuple[str, str]], stamp: str) -> str:
    W, H = 1200, 150
    cw = W / len(cells)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" role="img" aria-label="GitHub statistics">',
           f'  <rect width="{W}" height="{H}" fill="{p["bg"]}"/>']
    for i, (num, label) in enumerate(cells):
        cx = cw * i + cw / 2
        vw = 40 if len(num) <= 3 else (31 if len(num) <= 5 else 25)
        out.append(f'  <text x="{cx:.1f}" y="66" text-anchor="middle" font-family="{SANS}" '
                   f'font-size="{vw}" font-weight="700" letter-spacing="-0.6" fill="{p["ink"]}">{num}</text>')
        out.append(f'  <text x="{cx:.1f}" y="92" text-anchor="middle" font-family="{MONO}" font-size="11" '
                   f'letter-spacing="1.5" fill="{p["muted"]}">{label}</text>')
        if i:
            out.append(f'  <line x1="{cw * i:.1f}" y1="36" x2="{cw * i:.1f}" y2="100" '
                       f'stroke="{p["line"]}" stroke-width="1"/>')
    out.append(f'  <line x1="0" y1="118" x2="{W}" y2="118" stroke="{p["line"]}" stroke-width="1"/>')
    out.append(f'  <text x="4" y="140" font-family="{MONO}" font-size="10" letter-spacing="1.5" '
               f'fill="{p["muted"]}">GITHUB METRICS &#8212; AUTO-GENERATED, NO THIRD-PARTY SERVICE</text>')
    out.append(f'  <text x="{W - 4}" y="140" text-anchor="end" font-family="{MONO}" font-size="10" '
               f'letter-spacing="1.5" fill="{p["accent"]}">{stamp}</text>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def main() -> int:
    cells = collect()
    stamp = "UPD " + dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    OUT.mkdir(parents=True, exist_ok=True)
    for theme, p in PALETTES.items():
        (OUT / f"stats-{theme}.svg").write_text(svg(p, cells, stamp), encoding="utf-8")
    print("cells:", cells)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, RuntimeError, KeyError, TypeError) as exc:
        print(f"stats refresh failed: {exc}", file=sys.stderr)
        sys.exit(1)
