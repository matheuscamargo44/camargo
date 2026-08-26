# Spec — Instalock Smart Counter-Pick (OP.GG) + ARAM: Desordem augment overlay (removed)

Status as of **2026-08-24**. Part A shipped in v0.9.0; Part B is implemented and awaiting a live run.
This doc exists so a future session (or a compacted version of this one) doesn't have to re-derive the
empirically-verified facts below from scratch — including the approaches that were tried and **failed**,
which are the expensive part to rediscover.

## Origin

User asked to "connect the Instalock to Blitz" for pick suggestions. Investigated: Blitz exposes no
local port and no public API (confirmed live — checked every Blitz.exe process on the user's machine,
zero listening ports). Reverse-engineering their private cloud API was explicitly ruled out (ToS risk,
fragile, not a real integration). Pivoted to OP.GG, which **officially publishes** an MCP server for
this exact purpose.

## Part A — Shipped in v0.9.0

**What it does**: opt-in toggle on the Instalock card ("Smart Counter-Pick (OP.GG)", off by default).
When the enemy player in the same lane has locked their champion, Instalock checks OP.GG's lane-matchup
data for the user's own priority list (top 3 entries, in list order) and promotes the first one with a
confirmed lane advantage. Never introduces a champion outside the user's list. Any OP.GG failure
(offline, rate-limited, unknown champion key) silently falls back to the existing static-order behavior
— this was a hard requirement, not a nice-to-have.

### Data source — OP.GG's official MCP server

- Endpoint: `https://mcp-api.op.gg/mcp`. Published by OP.GG themselves at `github.com/opgginc/opgg-mcp`
  (MIT license, org account belongs to the company). No API key. No documented rate limit.
- Protocol: MCP "Streamable HTTP" transport = JSON-RPC 2.0 over HTTP POST.
  1. `POST {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{...}}}`
     → response header `Mcp-Session-Id: <uuid>` must be captured and echoed on every subsequent call.
  2. `POST {"jsonrpc":"2.0","method":"notifications/initialized"}` (required by MCP spec, no response body needed).
  3. `POST {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"lol_get_lane_matchup_guide","arguments":{"position":"top","my_champion":"GAREN","opponent_champion":"DARIUS"}}}`
     → `result.content[0].text` is a **JSON string** (needs a second `json.loads`), containing
     `data.lane_advantage_champion`, `data.recommended_play_style`, `data.opponent_champion_tip`, plus a
     lot of unrelated data (items, runes, general tier stats) that we discard.
- Full tool catalog has 30 tools (`tools/list`), including a fallback tier-list tool
  (`lol_list_lane_meta_champions`) not currently used, and `lol_list_aram_augments` (relevant to Part B).

### Champion-name normalization — fully verified empirically, no exceptions found

OP.GG wants `UPPER_SNAKE_CASE` champion keys. **These do NOT reliably match Riot's own internal `alias`
field** from `champion-summary.json` (e.g. Wukong's alias is `MonkeyKing`, Renata Glasc's is `Renata` —
both rejected by OP.GG). The rule that *does* work, derived from Riot's **display name** (`champ["name"]`,
the same field `Instalock.champ_dict` is already built from):

```
uppercase → strip "'" and "." → replace runs of whitespace/"&" with "_" → strip leading/trailing "_"
```

Verified live against the real endpoint, 13/13 correct, zero exceptions:

| Display name | OP.GG key | Display name | OP.GG key |
|---|---|---|---|
| Kai'Sa | `KAISA` | Dr. Mundo | `DR_MUNDO` |
| Vel'Koz | `VELKOZ` | Tahm Kench | `TAHM_KENCH` |
| Rek'Sai | `REKSAI` | Renata Glasc | `RENATA_GLASC` |
| Bel'Veth | `BELVETH` | Nunu & Willump | `NUNU_WILLUMP` |
| Kog'Maw | `KOGMAW` | Wukong | `WUKONG` |
| Cho'Gath | `CHOGATH` | Mel | `MEL` |
| Garen | `GAREN` | | |

Implemented as `to_opgg_champion_key()` in `backend/core/opgg_client.py`, unit-tested against this exact
table in `backend/tests/test_opgg_client.py`.

### Code

- **`backend/core/opgg_client.py`** (new) — `OpggClient`: owns the MCP session id, `_initialize()` does
  the 2-step handshake, `_call_tool()` retries once with a fresh session on any non-`OpggMcpError`
  failure (an `OpggMcpError` means the server understood and actively rejected the request — e.g. bad
  champion key — retrying won't help, so it's not treated as a stale-session signal). No TTL/background
  thread (unlike `ValorantClient`) — there's no "process restarted" trigger here, purely on-demand.
  Module-level singleton `opgg_client`, imported directly by `instalock.py` (deliberately **not** wired
  into `FeatureRegistry`'s per-feature client injection — single consumer today, not worth extending that
  mechanism yet).
- **`backend/features/instalock.py`**:
  - `champ_id_to_name` dict added alongside the existing `champ_dict` (name→id), built in the same
    `update_champion_list()` pass — needed to turn the enemy's `championId` back into a display name for
    the OP.GG call.
  - `_enemy_lane_champion_id(session, cell_id)` — pure, no I/O: finds the local player's
    `assignedPosition` in `myTeam`, finds the `theirTeam` entry with the same position, returns its
    `championId` (or `None` if not locked / no role structure).
  - `POSITION_MAP` — LCU's `TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY` → OP.GG's `top/mid/jungle/adc/support`.
  - `_smart_counter_pick(session, cell_id, available)` — the reactive logic; caches by
    `(my_champ_id, enemy_champ_id)` in `self._matchup_cache` (self-invalidates on a new enemy pick since
    the enemy id is part of the key; never explicitly cleared — bounded in practice, matches the existing
    unbounded `champ_dict` pattern).
  - `resolve_champion()` calls `_smart_counter_pick()` as a pre-step; if it returns `None` (disabled, no
    enemy lock yet, or nothing favorable found among the top 3), falls through to the original
    first-available-in-list behavior — completely unchanged for anyone who leaves the toggle off.
  - New config key `DEFAULT_CONFIG["instalock"]["smart_counter_pick"]` (bool, default `False`).
  - New action `toggle_smart_counter_pick(enable=None)`, mirrors the existing `toggle()` shape.
- **`desktop/src/views/forms.js`** — `FEATURE_TOGGLES.instalock` gained a second toggle entry
  (`{ field: "smart_counter_pick", label: "Smart Counter-Pick (OP.GG)", action: "toggle_smart_counter_pick" }`).
  No other frontend changes needed — `feature-card.js`'s multi-toggle rendering and the generic
  `POST /features/{key}/actions/{action}` dispatch already handled everything else.

### Tests

175 backend tests passing (was 153 before this session's instalock/mode work, +22 for this feature:
13 parametrized name-normalization cases, 3 `OpggClient` handshake/retry/error tests, 6
`Instalock`-level integration tests covering promote/disabled/no-enemy-lock/opgg-failure/caching).

### ⚠️ Open item — NOT yet confirmed live

**Does `/lol-champ-select/v1/session`'s `theirTeam[].championId` actually go non-zero *during* the draft
(when the enemy locks), or only at the loading screen?** This is the one fact the whole feature's
real-world usefulness depends on, and it could not be tested this session — no active champ select was
running on the user's machine when this was built. A design-review subagent argued convincingly (standard
Ranked/Normal Draft is one synchronous 10-player session, not two isolated lobbies — every League player
has watched an enemy portrait pop in mid-draft) that it should work, but this is reasoning, not a live
check.

**Action needed**: next time the user is in a real Ranked/Normal draft, watch the Logs tab for
`"Instalock: promoting <champ> - better matchup vs <enemy>"` after an enemy locks in the same lane, with
the toggle on. If it never fires despite an enemy having clearly locked, dump
`GET /lol-champ-select/v1/session` mid-draft and inspect `theirTeam[].championId` directly — that's the
single quickest way to root-cause it either way.

## Part B — ARAM: Desordem augment overlay — REMOVED (2026-08-26)

> **Removed from the product at the user's request**, after shipping through v0.15.1. Everything below is
> kept as history: it is the record of what was tried, what was measured live, and why each call was made —
> including several findings that cost real investigation (OP.GG's MCP silently omitting tiers 0-2, the
> per-rarity border tinting, the icon-correlation calibration). If this is ever revisited, start here rather
> than from scratch; the last working implementation is at tag `v0.15.1`.
>
> What went with it: `features/aram_augment_advisor.py`, `core/augment_vision.py`, `core/augment_catalog.py`,
> `core/aram_augment_regions.py`, `core/opgg_scraper.py`, the whole Electron overlay window
> (`overlay.html`/`overlay.js`/`overlay-preload.js`/`aram-overlay-controller.js`), and
> `OpggClient.get_aram_augments`. The `mss`/`Pillow`/`numpy` dependencies went with them — nothing else in
> the app captures the screen any more.
>
> What deliberately stayed: `core/opgg_client.py` (Part A's counter-pick still uses `get_lane_matchup`, and
> its class-repr parsing is transport machinery for any OP.GG tool) and `features/aram_bench_swap.py`, which
> is the ARAM bench-swap automation and never had anything to do with augments.

### Original design and research (historical)

**What it does**: opt-in toggle ("Aram Augments"). While in an ARAM: Desordem match, it detects the
augment picker appearing on screen, identifies the three offered augments from their icons, looks up
OP.GG's tier data for the played champion, and draws a click-through overlay badge under each card,
highlighting the best one. Badges disappear the moment the picker does.

This reverses the earlier "not building this" call recorded in this document — that decision was made on
the grounds of not duplicating Blitz/OP.GG desktop, and the user later asked for it directly.

### Why screen capture at all

No Riot-sanctioned API exposes which augments are being offered. Verified exhaustively: polled
`https://127.0.0.1:2999/liveclientdata/allgamedata` every 2s across a full real match, and read the
complete `/swagger/v3/openapi.json` contract — **zero** occurrences of "augment" in either. Confirmed
independently mid-investigation: the user's own Blitz overlay was drawing tier badges on the cards while
Blitz exposes no local port at all, so it can only be doing screen capture + image matching too.

### Requirements (OS-level constraints, not bugs)

- **Borderless / windowed mode.** An exclusive-fullscreen game can neither be captured by a desktop grab
  nor be drawn over by an overlay window. Blitz and the OP.GG desktop app carry the same requirement.
- **1920x1080 primary display.** The card geometry is calibrated for it; other resolutions report
  `unsupported_resolution` and the feature stays idle.

Failing either is harmless: the picker probe simply never matches, so nothing is shown — it never misfires.

### Detecting the picker (do not use the player's level)

The first design triggered on crossing champion level 7/11/15. That is **wrong**, and the calibration
screenshots proved it: levels 7 and 15 captured only a "you earned an Augment!" notification with no
cards on screen, because the player opens the picker whenever they choose. Only the level-11 shot caught
the real picker.

Replaced with direct detection: sample 9 pixels down each of the three cards' gold borders
(`CARD_BORDER_XS`, `core/aram_augment_regions.py`). Measured across all four calibration screenshots —
picker open scored **9/9 on all three borders**, every closed-picker shot scored **0-2**. A threshold of
7 sits in that gap. This also provides the close/hide edge for free.

### Icon matching — what failed, and what works

Three dead ends, all worth not repeating:

1. **Perceptual hash (`imagehash.phash`)** — far too coarse for small line-art glyphs. On a real capture
   it ranked the correct augment **39th of ~600**. The dependency has since been dropped entirely, which
   also removed `scipy` and `pywavelets`.
2. **Binary shape masks** — thresholding to "bright glyph on dark background" discards the dark swirl
   structure that actually distinguishes the glyphs; the art is two-tone.
3. **Detail-based auto-localisation of the glyph** — locked onto card chrome (borders, text) instead.

What works, in three parts:

- **Use the `_large` icon variant.** The catalog only ever gives `augmentSmallIconPath`, but many
  *different* augments share one byte-identical `_small` placeholder (612 files, only 313 distinct
  images). The `_large` file sitting beside it carries the real per-augment art.
- **Calibrate the crop geometry against ground truth, not by eye.** Card 0 in the calibration screenshot
  is known to be "Ethereal Weapon", so the crop was found by searching for the box maximising correlation
  with that reference: centre (598, 310), 160x160, correlating at **0.9704**. A hand-measured box ~10px
  off was enough to collapse every candidate score into a band **0.0000** wide — the right answer was
  "winning" purely by luck.
- **Normalised cross-correlation at 64x64** on the grayscale glyph, after compositing the transparent
  reference onto a dark background (skipping that composite alone cost 6 points of Hamming distance).
  With correct geometry: correct art scores **0.9696-0.9728**, best genuinely-different art **at most
  0.938**. A threshold of 0.95 sits cleanly between.

### Ambiguity policy — the part that keeps it honest

Even with `_large`, some genuinely different augments ship pixel-identical art (e.g. "Ok Boomerang",
"Endless Decimation", "And My Axe!" — verified byte-identical, and the in-game render matches that art
exactly). No image comparison can ever separate those, so `identify()` returns the whole tied candidate
set rather than picking one.

`AramAugmentAdvisor._resolve_candidates` then resolves it using OP.GG's per-champion data, which only
covers tier 3 and above:

| Case | Result |
|---|---|
| Exactly one candidate rated | show name + tier, eligible for "best" |
| Several rated, tiers agree | show tier, eligible for "best" |
| Several rated, tiers disagree | **drop the tier**, mark ambiguous, cannot win "best" |
| None rated | no tier — reliably means "worse than the rated cards", not "unknown" |

When ambiguous the **name is withheld** (`name: null`) and the overlay shows "Unknown": the matched *art*
is always correct, so the icon is safe to display; only which augment owns that art is uncertain.

Measured against a real champion pool (Ziggs, 133 augments): of 118 icon groups, **109 fully unambiguous,
5 ambiguous but tier-identical (harmless), 4 (3.4%) genuinely conflicting**.

### Tier direction and the S/A/B ranks

OP.GG's numeric augment tier runs **best-to-worst: lower is better**. Worth stating explicitly because
the tool's own description ("only tier 3 or higher are included") reads the other way and an inverted
comparison would recommend the *worst* card on offer. Verified two ways against live data:

- Mean performance by tier for Viego — T3 79.45, T4 78.49, T5 76.64.
- Shape of the distribution across five champions (Viego, Ziggs, Ezreal, Ahri, Garen): T3 is rare
  (4-16 per champion), T5 is the bulk (71-106). A quality pyramid, not a flat scale.

Only 3/4/5 are ever returned, so those three are the whole scale and map to `S`/`A`/`B` for display
(`TIER_RANKS` in `aram_augment_advisor.py`). The numeric tier stays the sort key; the letter is
presentation only. `test_lower_tier_numbers_are_better` guards the direction.

### End-to-end result on the real screenshot

Ground truth was Ethereal Weapon / Ok Boomerang / Sonata:

- slot 2 → identified as **Sonata, tier 4, unambiguous → recommended**
- slots 0 and 1 → correctly flagged ambiguous, no tier, excluded from "best"

Recommending slot 2 is the **correct** answer: the other two are absent from the tier-3+ pool, meaning
they rate below Sonata.

### Code

- `backend/core/live_client_data.py` (new) — thin client for the port-2999 API; returns `None` while no
  match is running (the normal idle state), never raises.
- `backend/core/augment_catalog.py` (new) — catalog fetch, `_large` icon vectors, disk cache
  (`augments.json` + `vectors.npz`), `identify()` returning a candidate list.
- `backend/core/augment_vision.py` (new) — `mss` capture plus `picker_is_open()`.
- `backend/core/aram_augment_regions.py` (new) — calibrated geometry and border-probe constants.
- `backend/features/aram_augment_advisor.py` (new) — the `ThreadedFeature`: gameflow gate → KIWI check →
  picker edge detection → capture → identify → tier resolve.
- `backend/core/opgg_client.py` — added `get_aram_augments()`, plus a parser for a response format this
  server uses that Part A never hit (see below).
- `backend/api/server.py` — added `GET /features/{key}` as a cheap single-feature poll target. The bulk
  `/features` poll runs at 4s and several features make their own LCU round-trip inside `get_status()`,
  so it is both too slow and too expensive to speed up for a several-second pick window.
- `desktop/main.js`, `desktop/overlay-preload.js`, `desktop/src/overlay.{html,js}` — the transparent,
  click-through, always-on-top overlay window. `setAlwaysOnTop(true, "screen-saver")` is what puts it
  above a borderless game; `showInactive()` keeps it from stealing focus.
- `desktop/src/aram-overlay-controller.js` — polls the narrow endpoint at 600ms, but only while the
  feature is enabled *and* League is connected; stops immediately otherwise.

### OP.GG response-format gotcha

Tools called with `desired_output_fields` (`lol_list_aram_augments`, `lol_get_champion_analysis`) do
**not** return JSON. They return a pseudo-Python "class repr" text:

```
class Data: augments
class Augment: id,name,tier,performance

LolListAramAugments(Data([Augment(2132,"Warlock Juicebox",3,79.89), ...]))
```

`lol_get_lane_matchup_guide` has no `desired_output_fields` in its schema and returns real JSON, which is
why Part A never hit this. `_parse_class_repr` in `opgg_client.py` handles both formats, including names
containing commas and apostrophes, and `null` literals.

### Verified vs still pending

Verified: picker detection (4/4 screenshots), icon matching and geometry (real capture against ground
truth), ambiguity policy (real champion pool), OP.GG augment lookup (live), PyInstaller packaging (frozen
exe run directly), 206 backend + 19 frontend tests.

**Confirmed live 2026-08-25**, by capturing the user's screen while the picker was open in a real match:
`picker_is_open()` returned True, and the overlay was drawing its badges over the three cards with the
best one outlined — the whole chain works end to end against the real game.

**Still pending**: the game-start picker specifically. Only the level-up reoffer has ever been captured,
so if the start picker sits elsewhere on screen the border probe will not fire there (harmlessly - it
shows nothing rather than something wrong).

**Watch out when debugging from source**: `identify()` returning nothing in a dev script usually means
the dev `backend/augment_cache/` was deleted and the catalog has not been rebuilt - the installed app
keeps its own cache under `%APPDATA%/camargo/`. That cost a wrong diagnosis once.

### Flapping fix (2026-08-25) — hovering a card to compare it briefly reads as "picker closed"

A real user session's log showed one continuous pick moment re-triggering `_on_picker_opened` **4 times
in 6 seconds**, all identifying the same card - only possible if `picker_is_open()` was flickering while
the picker never actually closed. User-visible symptom: the recommendation badges flashed on and off, and
occasionally a pick window ended with no recommendation shown at all.

Root cause: comparing augment cards means hovering each one in turn, and League's own UI **enlarges the
hovered card**. That shifts its border away from the fixed pixel column `picker_is_open()` samples,
dropping that one card below `CARD_BORDER_MIN_HITS` - and the original check required all 3 columns to
pass. The exact act of deciding which card to pick was what made the picker read as closed.

Two independent fixes, not one, because they cover different failure windows:

1. **Read side** (`CARD_BORDER_REQUIRED_COUNT = 2` in `aram_augment_regions.py`): `picker_is_open()` now
   passes on 2-of-3 borders instead of 3-of-3, so hovering one card no longer fails the whole check. A
   genuinely closed picker still reads 0-of-3, so the two states stay cleanly separated - reverified
   against every real screenshot on hand (both calibration shots and live diagnostic captures) after the
   change, all still classified correctly.
2. **Debounce** (`CLOSE_DEBOUNCE_TICKS = 3` in `aram_augment_advisor.py`): a second, independent safety
   net - the open→closed edge now requires 3 consecutive closed readings (≈1.5s) before clearing the
   recommendation, so any remaining single-frame noise (not just the hover case) can't wipe the badge
   mid-decision. The open edge stays immediate; only closing is debounced, since a late badge appearing is
   free but a badge vanishing while the player is looking at it is the whole complaint.

Also added a capture retry (`CAPTURE_ATTEMPTS = 3` in `_on_picker_opened`): a capture landing on a
half-drawn frame can legitimately identify nothing even with the picker genuinely open, so it's retried a
couple of times (same `CAPTURE_SETTLE_SECONDS` spacing) before giving up on that pick window, instead of
one miss meaning no recommendation for the whole card screen.

### OP tier and per-card justification (2026-08-25)

Two follow-up requests: does the recommendation account for the champion (yes, already did - the tier
lookup is per-champion), and could it call out a top "OP" tier above S with a stated reason per card.

**OP tier**: checked live whether tier 3 itself has real internal spread before adding anything - it does
(Viego's tier-3 performance runs 72.1-88.0, Garen's 63.2-81.8), so the single best-performing tier-3
augment for that champion (or any tied within `OP_PERFORMANCE_MARGIN = 1.0`) now reads as `OP`, the rest
of tier 3 stays `S`. Deliberately **not** implemented as a global performance sort: tier 5 (the worst
bucket) includes augments scoring well above tier 3's real range - checked live, up to 170 against tier
3's ~88 max, a low-sample-size artifact rather than genuine strength. Comparing performance is only ever
done *within* a tier OP.GG has already put in the same bucket, never across tiers - seeded a specific
regression test (`test_performance_never_promotes_across_tiers`) for that.

**Justification text**: OP.GG has no textual "why" for augments - the `desc` field that exists (confirmed
live, and it comes back correctly localized for `lang=pt_BR`) is just the augment's own generic
description, the same text already printed on the card, not champion-specific reasoning. So the
justification only ever states what's actually known: the tier grade in words, plus the real performance
score - but **only for OP/S**, where performance is the trustworthy signal. Appending it to an A/B card
would be misleading given the cross-tier noise above (a genuine live example: a "B" tier-5 card scoring
170 sitting next to an "OP" tier-3 card scoring 88 - showing both numbers invites exactly the wrong
conclusion). No invented flavor text about synergy or mechanics - there is no data to back that.

**Badge position**: moved from below the card's icon (where it visually collided with the card's own
name/description text, confirmed in a real screenshot) to above the whole card, bottom-anchored in CSS so
the box grows upward regardless of how many lines the justification wraps to.

**Dead field cleanup**: `recommendation.trigger` was left over from the level-based trigger design,
already replaced by direct picker detection - the frontend's dedup key was still referencing it (silently
becoming `"undefined:<champion>"`). Fixed to key on the actual identified augment ids, which also fixes a
real bug: the same champion getting a second, genuinely different offer (e.g. after a reroll) would have
been silently skipped as "already shown".

### Rarity-blind border detection (2026-08-25) — the picker was invisible on a real Silver-rarity offer

User report: "não está funcionando" on a real pick screen, right after the OP/S/A/B work above shipped.
Confirmed live by screenshotting the user's actual screen mid-pick: the picker was genuinely on screen,
but `picker_is_open()` read False.

Root cause, found by sampling raw pixels from the real capture: augments have a **rarity**, and the card
border is tinted per rarity, not one fixed color. Checked the full Community Dragon catalog for every
rarity value that exists - there are 5 (`kSilver`, `kGold`, `kPrismatic`, `kBronze`, `kEventChoice`), not
the 3 casually mentioned in Part B's original research. The detector had only ever been calibrated against
one real screenshot, which happened to show a Gold-rarity offer (border ≈ `(173,145,116)`, warm). This
user's real offer was Silver-rarity (border ≈ `(137,138,137)`, neutral grey) - a completely different hue,
which the original warm-gold-specific color check (`red>150, blue<140, red-blue>40`) never matched. This
is exactly what the user's own follow-up called out: the rarity system should have been researched instead
of calibrating against whichever single screenshot happened to be on hand.

Fixed by making the check brightness-based instead of hue-based: a card border only needs to be
meaningfully brighter than the near-black card interior (`(3-10, 15-38)` sampled from real captures)
without being near-pure-white (which reads as UI text/glow, not a card frame) -
`_BORDER_BRIGHTNESS_RANGE = (80, 250)` in `augment_vision.py`. Verified this doesn't just trade one blind
spot for another: re-ran it against every real capture on hand (both rarities now seen live, plus all 8
known-closed negatives, including the specific one that broke an even looser, uncapped version of this
same check - real world lighting/VFX bleeding through the dimmed background at these exact coordinates hit
9/9 brightness-only hits on one column, which only stayed correctly classified as closed because
`CARD_BORDER_REQUIRED_COUNT` still requires 2 of 3 columns to agree, not just one).

Icon *identification* needed no change at all and was re-verified working on the real Silver-rarity
capture without modification: the reference vectors are built from Community Dragon's raw grayscale-mask
icons, which carry no rarity tint to begin with (the color is a real-time render effect, not baked into
the asset) - only the border-detection side was ever rarity-specific.

Prismatic/Bronze/EventChoice have not been seen in a live capture yet, so their exact border color is
still unconfirmed - the brightness-only approach is the hedge against that gap (no hue assumption to break
this time), not a claim that all 5 have been individually verified.

**Follow-up, same day**: the brightness-range fix above was itself still a hue assumption in disguise (a
saturated color can have one dark channel, failing a "both channels bright" check) - flagged by the user
specifically asking about Prismatic ("cartas roxas") before it was ever seen live. Replaced with a
genuinely hue-agnostic check: rather than testing individual pixels against any absolute color, each
border column is tested for **self-consistency** - are most of its 9 sampled rows close to their own
median color. A painted border is one solid color for its whole length; the two known false-positive
sources (world lighting bleeding through the dimmed background, spell VFX) vary sample to sample even when
individually bright - confirmed live, one case swung from `(82,152,255)` to `(240,171,255)` across two
rows 20px apart. This works for any rarity's border color without needing to have seen it, which the
previous two versions did not achieve. `_is_card_border_column` in `augment_vision.py`.

### Unrated augments read as a verdict, not a data gap (2026-08-25)

User report: "Not among the stronger augments" showed up on most cards. Investigated whether Prismatic
augments were being systematically excluded from OP.GG's rated data (a real, reasonable suspicion given
the report) - they are not: 43 of Viego's 193 Prismatic augments are rated, same as any other rarity.

The real explanation is coverage, not exclusion: only ~22% of a champion's full augment pool (135 of ~600
for Viego) ever gets a tier from OP.GG at all - almost certainly a minimum-sample-size cutoff on their
side, not every excluded augment being confirmed weak. With that little coverage, basic probability says
roughly 88% of random 3-card offers will have at least 2 unrated cards - so seeing this message on most
cards every time is the expected case, not a malfunction.

The actual bug was the wording: "Not among the stronger augments... in this data" reads as a negative
verdict about the augment, when it should read as "no information available". Reworded to
`"No OP.GG performance data for this pick with {champion}."` - same underlying logic, just no longer
implying a judgment the data doesn't support.

### Researched whether a better data source exists (2026-08-25) — it doesn't, this is a real cold-start gap

User wanted the "no data" case actually solved, not just reworded, and asked to research how other
platforms handle it. Checked directly rather than assuming:

- **OP.GG's own website** (`op.gg/lol/modes/aram-mayhem/{champion}/build`) shows only 10 curated augments
  per champion, no win rate or tier at all - less data than the MCP tool already gives.
- **The same MCP tool, without `champion_id`**: the JSON schema doesn't mark it required, so tried calling
  without it hoping for a global (higher-sample-size) tier list. The server rejects this at the business
  logic layer regardless of what the schema says - `champion_id` is hard-required in practice.
- **The `popular` (pick rate) field**: checked whether it had broader coverage than `tier` as a fallback
  signal - it does not; it's returned for the exact same filtered 135-augment set, not a wider one.
- **U.GG's augment tier list** - blocked the fetch (403).
- **aramgg.com** - a real tier list, but only 207 augments total (not per-champion), sourced from
  "Tencent China public statistics" - a different regional population, and not a source with the kind of
  transparency/sanctioning that justified building on OP.GG's MCP in the first place.
- **arammayhem.com** - does show real per-champion-per-augment win rates, but discloses no data source and
  no API - integrating with it would be the exact thing already ruled out for Blitz earlier in this
  project (reverse-engineering an opaque third party).

Conclusion: this isn't a solved problem elsewhere that camargo is failing to plug into. Real
per-champion-per-augment win-rate data is inherently sparse - roughly 600 augments × ~170 champions is far
more combinations than there are augment-pick events to reliably rate most of them, and OP.GG's own
website reflects that same sparsity (curated picks, not full stats, on their per-champion page).

**What shipped instead**: augment *rarity* (Silver/Gold/Prismatic/...) is static game data, present for
100% of augments regardless of statistical coverage - unlike tier, it can never be missing. An unrated
card's justification now names it: `"No OP.GG performance data for this Prismatic pick with {champion}."`
- verified live against real unrated Prismatic augments for Viego. Not a quality signal (rarity is
intentionally not strictly "better" - it's about how build-defining the effect is), but it keeps a
no-data card from reading as completely blank. `AugmentCatalog.rarity()`, `RARITY_LABELS` in
`aram_augment_advisor.py`.

### Correction: OP.GG's own site *does* have fuller data — the above research checked the wrong page (2026-08-26)

The "researched whether a better data source exists" conclusion above was wrong on its central claim. It
checked `op.gg/lol/modes/aram-mayhem/{champion}/build` (a curated 10-augment preview with no stats) and
stopped there. The champion's dedicated `.../{champion}/augments` page was never checked, and that page
embeds the full per-augment dataset server-side (a Next.js React Server Component payload in the raw HTML
- no headless browser needed, a plain GET already returns it).

Diffed it directly against the MCP tool's own output for Viego to be sure it's the same underlying numbers
and not a different computation: id 1103 "Bread And Butter" comes back as `tier 3, performance 72.1` from
both. Identical. But the *coverage* differs enormously:

- The website tracks **six** tiers, 0 (best) through 5 (worst) - not three.
- The MCP tool only ever returns tiers 3-5. For Viego that's 135 of 200 real augments (not "~600" as
  guessed in the section above - that figure conflated the game's whole augment roster across every mode
  with the much smaller pool actually offered to one champion in ARAM Mayhem).
- The 65 augments the MCP omits are tiers 0-2 - the champion's three *best* bands, not obscure ones.
  Confirmed live: tier 0's performance for Viego runs 76.5-88.7 and tier 1's 71.1-102.2, both tight and
  sane - nothing about them looks like a data-quality reason to withhold them.

So the "no OP.GG data" card shown on most 3-card offers was frequently not a genuine cold-start gap at
all - it was often the champion's *strongest* augment, simply never asked about because the sanctioned MCP
tool structurally can't return it.

**What shipped**: `core/opgg_scraper.py` reads the champion's `.../augments` page directly and returns the
full 0-5 range; `AramAugmentAdvisor._tier_data_for_champion` tries it first and only falls back to the MCP
tool (`opgg_client.get_aram_augments`) if the scrape comes back empty (network down, or OP.GG changed the
page's internal structure - this is unavoidably more fragile than the documented MCP, hence keeping the
MCP as a safety net rather than removing it). `TIER_RANKS` now groups the six raw tiers two-per-letter
(`{0: "S", 1: "S", 2: "A", 3: "A", 4: "B", 5: "B"}`) so the on-screen OP/S/A/B vocabulary didn't need to
grow; OP is now carved out of tier 0 instead of tier 3, using the same margin technique as before.

This does not reopen the Riot-policy question raised earlier in this session (`developer.riotgames.com`'s
"Products cannot display win rates for Augments" line) - the display already showed OP.GG win-rate-derived
tier/performance data before this change; this only changes which of OP.GG's own numbers get read, not
whether numbers are shown at all. It does raise the same fragility trade-off already accepted for
`augment_catalog`'s icon matching: this reads OP.GG's undocumented internal page structure, and will need
re-calibrating if they rebuild that page.

### Rarity fallback: the player always wants an answer, even a weak one (2026-08-27)

User feedback, stated directly: the player always wants the strongest of the 3 offered cards highlighted -
"no highlight anywhere" (the previous behavior whenever none of the 3 had real OP.GG data, or an icon was
ambiguous) reads as a bug, not as honesty, from the player's side of the screen.

Researched whether there's an established answer for this specific case (all 3 offered cards genuinely
unrated) before picking one. Two findings:

- **Rarity really is Riot's own documented power signal**, not a community guess or something invented for
  this fallback: Prismatic is officially described as carrying "the most powerful, game-changing effects",
  Gold "strong effects", Silver "basic stat boosts and utility". A legitimate last-resort tiebreaker.
- **No competing tool solves this live.** Blitz, OP.GG's own site, U.GG, and Mobalytics all publish
  pre-curated "recommended augments" guides - lists of *already-good* augments picked ahead of time - not a
  live reaction to whichever 3 specific cards a real pick screen just offered. None of them document a
  "what if none of these 3 has data" fallback, because their product shape never has to answer it. This
  tool does (it reacts to the real offer), so there was no existing answer to adopt - this is a genuine
  product decision, made here rather than found.

**What shipped**: when the real tier/performance pass leaves every card unranked, `_apply_rarity_fallback`
(`aram_augment_advisor.py`) picks the highest-rarity of the 3 (Prismatic > Gold > Silver) as a `GUESS_RANK`
pick - `recommendation["best_slot_is_guess"]` flags it so the badge never looks like a data-backed OP/S/A/B.
The card's own justification names the rarity and says plainly it isn't data-backed. Ambiguous cards (no
known rarity, since identity itself is unknown) are excluded from the fallback pool the same as everywhere
else in this pipeline. If even rarity is unknown for all 3 (an unrecognized rarity string), `best_slot`
stays honestly empty - there is truly nothing left to guess with at that point.

Visually: the guess still gets the "best" border highlight so it stands out from the other 2 unhighlighted
cards, but dashed and amber instead of solid blue, and its rank pill reads "Guess" as an amber outline
instead of a solid OP/S/A/B fill - recognizable as lower-confidence from across the screen, not just on
close reading of the text. See `.is-guess` / `.rank-guess` in `overlay.html`.

### Reroll left stale badges over cards that were no longer there (2026-08-26)

Known gap, documented in the code as deliberately-unfixed since the close-debounce work, now closed.

**The bug**: rerolling swaps all 3 cards, but the picker does not reliably read as *closed* while it
happens. `CLOSE_DEBOUNCE_TICKS` requires 3 consecutive closed readings (1.5s) before believing a close, and
a reroll either never produces that many or closes and reopens entirely between two 500ms polls. Either
way `_picker_was_open` never drops to False, `_on_picker_opened` never fires again, and the pre-reroll
recommendation stays on screen — badges sitting over three cards that are no longer the ones being offered.
Actively misleading, which is worse than the "no recommendation" every other failure path degrades to.

**Why the obvious fix was already tried and reverted**: re-capturing on any *partial* closed streak
reintroduces exactly the re-trigger the debounce exists to prevent. Hovering a card to compare it draws it
enlarged, which drops its border out of the fixed sample column and reads as closed — confirmed live, one
real pick moment re-triggered 4 times in 6s. From `picker_is_open()` alone a hover flicker and a reroll are
indistinguishable, so no amount of tuning the presence signal separates them.

**What shipped**: stop asking whether the picker is still open and ask whether it is still showing *the same
offer*. `_offer_signature_of()` takes the identity of what is on screen — the raw per-slot candidate id sets
from `identify()`, deliberately captured *before* `_resolve_candidates` collapses them, since resolution
depends on OP.GG data that can change across a cache refresh while the screen has not. `_check_for_reoffer()`
re-reads each tick while the picker is up and diffs against what the current recommendation was built from.

Two guards keep this from becoming the reverted fix in another form:

- **A partial read is never evidence.** A hovered card identifies as nothing, so the read comes back with
  fewer than 3 slots — ignored outright. This is the primary defence, and it is the exact signature of the
  hover case that broke the previous attempt.
- **A new identity must repeat** (`REOFFER_CONFIRM_TICKS = 2`) before it is acted on, covering a single
  mid-animation frame that happens to match some other augment. A partial read does *not* reset the streak:
  a reroll's own fade-in produces partial frames between the two good reads of the new cards, and resetting
  there would keep the stale badges up through a slow fade.

Affordable to run every tick: a full re-read measures ~30ms (22ms capture + 7ms correlating all 3 cards
against the 612 reference vectors) against a 500ms poll, and only runs while the picker is actually open —
seconds per game. It is also skipped entirely when no recommendation is showing, so the idle path pays
nothing.

No frontend change was needed: the overlay controller already keys its dedup on `slot:augment_id`, so a
rebuilt recommendation with new ids re-renders on its own.

**Side effect worth naming**: this also upgrades a *partial* recommendation. If the opening capture only
ever managed to read 2 of 3 cards (accepted as a fallback after exhausting retries), the next full read
differs from that 2-slot signature and rebuilds with all 3 — so a card that was missing at fade-in now
appears instead of being absent for the rest of the pick.
