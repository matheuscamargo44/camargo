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
        return json.loads(text)

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


#: Shared across every consumer (currently just Instalock) - one MCP
#: session, not one per feature.
opgg_client = OpggClient()
