"""Thin client for OP.GG's official MCP server (mcp-api.op.gg).

OP.GG publishes this themselves (github.com/opgginc/opgg-mcp, MIT) - no
API key, no documented rate limit. MCP's "Streamable HTTP" transport is
just JSON-RPC 2.0 over HTTP POST: an `initialize` call returns a session
id (in the `Mcp-Session-Id` response header) that every following call
must echo back. There's no local process to restart here the way League/
VALORANT's clients get restarted, so unlike ValorantClient there's no TTL
on the session - it's simply re-initialized on demand if a call fails.
"""
import json
import logging
import re
import threading

import requests

logger = logging.getLogger(__name__)

MCP_URL = "https://mcp-api.op.gg/mcp"
REQUEST_TIMEOUT_SECONDS = 4.0
PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "camargo", "version": "1.0.0"}

_BASE_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

#: OP.GG expects UPPER_SNAKE_CASE champion keys that do NOT always match
#: Riot's own internal `alias` field (e.g. Wukong's alias is "MonkeyKing",
#: Renata Glasc's is "Renata" - both wrong for OP.GG). Empirically verified
#: live against every apostrophe/period/space/& champion name in the
#: roster: strip apostrophes and periods, turn spaces/& into underscores.
_STRIP_CHARS = re.compile(r"[.']")
_SEPARATOR_CHARS = re.compile(r"[\s&]+")


def to_opgg_champion_key(display_name: str) -> str:
    stripped = _STRIP_CHARS.sub("", display_name)
    return _SEPARATOR_CHARS.sub("_", stripped).strip("_").upper()


#: Tools called with `desired_output_fields` (e.g. `lol_list_aram_augments`)
#: don't return plain JSON - they return a compact pseudo-Python "class
#: repr" text instead, e.g.:
#:   class Data: augments
#:   class Augment: id,name,tier,performance
#:
#:   LolListAramAugments(Data([Augment(2132,"Warlock Juicebox",3,79.89), ...]))
#: Confirmed live this session: `lol_get_lane_matchup_guide` (no
#: `desired_output_fields` in its schema at all) returns real JSON, but
#: `lol_list_aram_augments` and `lol_get_champion_analysis` (both of which
#: accept `desired_output_fields`) return this instead. Parsed here into
#: plain dicts/lists so callers never need to know which format came back.
_CLASS_DECL_RE = re.compile(r"^class (\w+): (.+)$")
_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|-?\d+\.\d+|-?\d+|[A-Za-z_]\w*|[\[\]\(\),]')


def _unescape_class_repr_string(token):
    return token[1:-1].replace('\\"', '"').replace("\\\\", "\\")


def _parse_class_repr(text):
    lines = text.splitlines()
    class_fields = {}
    expr_start = len(lines)
    for i, line in enumerate(lines):
        match = _CLASS_DECL_RE.match(line)
        if not match:
            expr_start = i
            break
        class_fields[match.group(1)] = [f.strip() for f in match.group(2).split(",")]

    tokens = _TOKEN_RE.findall("\n".join(lines[expr_start:]).strip())
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def consume(expected=None):
        nonlocal pos
        token = tokens[pos]
        if expected is not None and token != expected:
            raise ValueError(f"expected {expected!r}, got {token!r}")
        pos += 1
        return token

    def parse_value():
        token = peek()
        if token is None:
            raise ValueError("unexpected end of OP.GG class-repr response")
        if token.startswith('"'):
            return _unescape_class_repr_string(consume())
        if token == "[":
            consume("[")
            items = []
            if peek() != "]":
                items.append(parse_value())
                while peek() == ",":
                    consume(",")
                    items.append(parse_value())
            consume("]")
            return items
        if token in ("True", "False", "true", "false"):
            return consume().lower() == "true"
        if token in ("None", "null"):
            consume()
            return None
        if re.fullmatch(r"-?\d+\.\d+", token):
            return float(consume())
        if re.fullmatch(r"-?\d+", token):
            return int(consume())
        # Otherwise it's a class name: IDENT "(" args... ")"
        class_name = consume()
        consume("(")
        args = []
        if peek() != ")":
            args.append(parse_value())
            while peek() == ",":
                consume(",")
                args.append(parse_value())
        consume(")")
        fields = class_fields.get(class_name)
        if fields is None:
            return args
        return dict(zip(fields, args, strict=False))

    return parse_value()


def _parse_tool_result_text(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _parse_class_repr(text)


class OpggMcpError(Exception):
    """The MCP server responded, but with a JSON-RPC error (e.g. an
    invalid champion/position combination), not a transport failure."""


class OpggClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._session_id = None

    def _initialize(self):
        response = requests.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            },
            headers=_BASE_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        session_id = response.headers.get("Mcp-Session-Id")
        if not session_id:
            raise RuntimeError("OP.GG MCP server did not return a session id")

        headers = {**_BASE_HEADERS, "Mcp-Session-Id": session_id}
        requests.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        self._session_id = session_id

    def _call_tool_once(self, name, arguments):
        headers = {**_BASE_HEADERS, "Mcp-Session-Id": self._session_id}
        response = requests.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        envelope = response.json()

        if "error" in envelope:
            raise OpggMcpError(envelope["error"].get("message", "OP.GG MCP call failed"))

        text = envelope["result"]["content"][0]["text"]
        return _parse_tool_result_text(text)

    def _call_tool(self, name, arguments):
        """Runs an MCP tool call, re-initializing the session once if it
        looks stale. `OpggMcpError` (a valid response the server actively
        rejected, e.g. an unknown champion key) is not stale-session
        territory, so it passes straight through instead of retrying.
        """
        with self._lock:
            if self._session_id is None:
                self._initialize()
            try:
                return self._call_tool_once(name, arguments)
            except OpggMcpError:
                raise
            except Exception:
                self._session_id = None
                self._initialize()
                return self._call_tool_once(name, arguments)

    def get_lane_matchup(self, my_champion_name, opponent_champion_name, position):
        """Lane matchup guidance for `my_champion_name` versus
        `opponent_champion_name` in `position` (top/mid/jungle/adc/support).
        Both names are Riot's display names (e.g. "Kai'Sa", "Dr. Mundo") -
        normalized to OP.GG's expected key internally.
        """
        result = self._call_tool(
            "lol_get_lane_matchup_guide",
            {
                "position": position,
                "my_champion": to_opgg_champion_key(my_champion_name),
                "opponent_champion": to_opgg_champion_key(opponent_champion_name),
            },
        )
        data = result.get("data", {})
        return {
            "lane_advantage_champion": data.get("lane_advantage_champion"),
            "recommended_play_style": data.get("recommended_play_style"),
            "opponent_champion_tip": data.get("opponent_champion_tip"),
        }



    def get_champion_counters(self, champion_name, position):
        """Champions that beat `champion_name` in `position`, best first.

        Reads the target's own `weak_counters` - the champions it loses to -
        which is exactly "what should I pick against them", in one call.
        Asking the inverse question (does candidate X beat them?) would cost
        one call per candidate, and each call measures ~3s against a pick
        window of roughly 30s.

        `counter_win_rate` is the *counter's* win rate in that matchup, not
        the target's, so it is already the number to show the player.
        """
        result = self._call_tool(
            "lol_get_champion_analysis",
            {
                "game_mode": "RANKED",
                "champion": to_opgg_champion_key(champion_name),
                "position": position,
                "lang": "en_US",
                "desired_output_fields": [
                    "data.weak_counters[].{champion_name,counter_win_rate}"
                ],
            },
        )
        counters = (result.get("data", {}) or {}).get("weak_counters") or []
        return [
            {"name": entry["champion_name"], "win_rate": entry["counter_win_rate"]}
            for entry in counters
            if entry.get("champion_name") and entry.get("counter_win_rate") is not None
        ]

#: Shared across every consumer (currently just Instalock) - one MCP
#: session, not one per feature.
opgg_client = OpggClient()
