"""Scrapes OP.GG's own ARAM: Mayhem augment page for a champion.

OP.GG's official MCP tool (`opgg_client.get_aram_augments`) only ever
returns augments in tiers 3-5 out of the six tiers (0-5, lower is better)
that OP.GG's own website actually tracks. Confirmed live by diffing a real
scrape against the MCP's own output for Viego: every entry the MCP does
return matches the site exactly (id 1103 "Bread And Butter": tier 3,
performance 72.1 in both), but the MCP silently omits every augment in
tiers 0-2 - the champion's three *best* bands (65 of Viego's 200) - and
only ever hands back the bottom half of OP.GG's own scale. That is why
cards kept showing "no OP.GG data": the MCP was never even asked about a
champion's strongest augments.

There is no documented API for this - it's a Next.js React Server
Component payload embedded in the page's own HTML (a
`self.__next_f.push([...])` script chunk), not a separate JSON endpoint.
Fetching the page with plain `requests` already returns it fully
server-rendered (confirmed live: no extra XHR fires for it, and a plain
GET's body contains the same data a rendered browser tab does), so no
headless browser/Selenium is needed here, unlike every other scraper of
this page found in the wild.

This is inherently fragile against an OP.GG frontend rebuild - it reads an
internal, undocumented payload shape that could change on any deploy. It
degrades to an empty dict on any parse failure, same as every other data
source in this app, and `AramAugmentAdvisor` falls back to the official
MCP tool when this comes back empty rather than showing nothing.
"""
import logging
import re

import requests

logger = logging.getLogger(__name__)

AUGMENTS_PAGE_URL = "https://op.gg/lol/modes/aram-mayhem/{alias}/augments"
REQUEST_TIMEOUT_SECONDS = 6.0

#: A plain browser UA - OP.GG's edge network has been observed to vary
#: response shape for obvious script default UAs (e.g. python-requests).
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

#: Matches one augment entry's leading fields in the embedded RSC payload,
#: e.g. {\"id\":1103,\"tier\":3,\"performance\":72.1,... - deliberately
#: stops right after `performance`. The fuller field set (name/desc/
#: tooltip/rarity) is free-text with escaped HTML and quotes, which made a
#: stricter match silently under-count (171 of 200 real entries in
#: testing, some entries skipped because a later match's start fell inside
#: an earlier match's greedy free-text span). Identity and display name
#: already come from `augment_catalog` (Community Dragon), so only the
#: three numeric fields actually needed are matched here.
_ENTRY_RE = re.compile(r'\{\\"id\\":(\d+),\\"tier\\":(\d+),\\"performance\\":([\d.]+)')


def scrape_aram_augments(champion_alias: str) -> dict:
    """Full-pool tier/performance data for `champion_alias` - Riot's
    DataDragon champion key (e.g. "Viego", "MonkeyKing", "KaiSa"), which is
    exactly OP.GG's own URL slug lowercased (verified against every
    apostrophe/period/space/& champion name in the roster: MonkeyKing ->
    monkeyking, DrMundo -> drmundo, KaiSa -> kaisa, RekSai -> reksai,
    Khazix -> khazix, Renata -> renata, KSante -> ksante).

    Returns {augment_id: {"id", "tier", "performance"}} - same shape as
    `opgg_client.get_aram_augments` - covering every tier (0 best, 5 an
    OP.GG catch-all for too-few-samples to trust; verified live: tier 5's
    performance spans 0-170 for Viego against a tight ~65-90 band across
    tiers 0-4). Tier 5 is kept rather than filtered here, matching how the
    MCP-sourced data was always treated: OP.GG's own tier is trusted as the
    primary signal even where it looks noisy (see `augment_rank`).

    Returns {} on any failure - network down, unknown champion, or the
    page's internal structure having changed - never raises.
    """
    url = AUGMENTS_PAGE_URL.format(alias=champion_alias.lower())
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
    except Exception:
        logger.debug("failed to fetch OP.GG augments page for %s", champion_alias, exc_info=True)
        return {}

    augments = {}
    for match in _ENTRY_RE.finditer(response.text):
        # Per-entry, not wrapping the whole loop: one malformed numeric
        # token (e.g. a stray "1.2.3" the [\d.]+ performance group can
        # match) used to raise out of the loop and discard every entry
        # already parsed - up to 199 good rows lost over one bad one.
        try:
            augment_id = int(match.group(1))
            tier = int(match.group(2))
            performance = float(match.group(3))
        except ValueError:
            logger.debug("skipping a malformed OP.GG augment entry for %s: %r", champion_alias, match.group(0))
            continue
        augments[augment_id] = {"id": augment_id, "tier": tier, "performance": performance}
    return augments
