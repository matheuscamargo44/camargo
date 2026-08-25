"""OpggClient: the MCP client behind Instalock's smart counter-pick.

Champion-name normalization is tested against every apostrophe/period/
space/& name verified live against the real OP.GG server this session -
these are not guesses, they are the exact keys that were confirmed to work
(and, for the wrong-looking alternatives, confirmed to fail).
"""
import json

import pytest

from core.opgg_client import OpggClient, OpggMcpError, _parse_class_repr, to_opgg_champion_key


@pytest.mark.parametrize(
    "display_name,expected",
    [
        ("Garen", "GAREN"),
        ("Kai'Sa", "KAISA"),
        ("Vel'Koz", "VELKOZ"),
        ("Rek'Sai", "REKSAI"),
        ("Bel'Veth", "BELVETH"),
        ("Kog'Maw", "KOGMAW"),
        ("Cho'Gath", "CHOGATH"),
        ("Dr. Mundo", "DR_MUNDO"),
        ("Tahm Kench", "TAHM_KENCH"),
        ("Renata Glasc", "RENATA_GLASC"),
        ("Nunu & Willump", "NUNU_WILLUMP"),
        ("Wukong", "WUKONG"),
        ("Mel", "MEL"),
    ],
)
def test_to_opgg_champion_key(display_name, expected):
    assert to_opgg_champion_key(display_name) == expected


def test_parse_class_repr_matches_a_real_captured_response():
    """Tools called with desired_output_fields (e.g. lol_list_aram_augments)
    don't return JSON - they return this pseudo-Python class-repr text.
    This exact text was captured live against the real OP.GG MCP server
    this session (champion_id=81, Ezreal)."""
    text = (
        "class LolListAramAugments: data\n"
        "class Data: augments\n"
        "class Augment: id,name,tier,performance\n"
        "\n"
        'LolListAramAugments(Data([Augment(2132,"Warlock Juicebox",3,79.89),'
        'Augment(1322,"Get Excited!",4,79.89),'
        'Augment(2089,"Yowch, My Coins!",4,74.41),'
        'Augment(1026,"Don\'t Blink",5,84.79),'
        "Augment(1337,\"King Me\",4,85),"
        "Augment(1250,null,5,80.79)])))"
    )
    result = _parse_class_repr(text)
    augments = result["data"]["augments"]
    assert augments[0] == {"id": 2132, "name": "Warlock Juicebox", "tier": 3, "performance": 79.89}
    # Names containing a comma or an apostrophe must not break tokenization.
    assert augments[2] == {"id": 2089, "name": "Yowch, My Coins!", "tier": 4, "performance": 74.41}
    assert augments[3] == {"id": 1026, "name": "Don't Blink", "tier": 5, "performance": 84.79}
    # An int-valued field (no decimal point) must parse as int, not str.
    assert augments[4] == {"id": 1337, "name": "King Me", "tier": 4, "performance": 85}
    # A `null` (JSON style, not Python's `None`) must parse as None.
    assert augments[5] == {"id": 1250, "name": None, "tier": 5, "performance": 80.79}


def make_class_repr_tool_response(text):
    return FakeResponse(json_data={"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": text}]}})


def test_get_aram_augments_parses_the_class_repr_response(monkeypatch):
    text = (
        "class LolListAramAugments: data\n"
        "class Data: augments\n"
        "class Augment: id,name,tier,performance\n"
        "\n"
        'LolListAramAugments(Data([Augment(2132,"Warlock Juicebox",3,79.89)]))'
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        if json.get("method") == "initialize":
            return FakeResponse(headers={"Mcp-Session-Id": "sess-1"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse()
        if json.get("method") == "tools/call":
            assert json["params"]["arguments"]["champion_id"] == 81
            return make_class_repr_tool_response(text)
        raise AssertionError(f"unexpected method: {json.get('method')}")

    import core.opgg_client as opgg_client_module

    monkeypatch.setattr(opgg_client_module.requests, "post", fake_post)

    client = OpggClient()
    result = client.get_aram_augments(81)

    assert result == {2132: {"id": 2132, "name": "Warlock Juicebox", "tier": 3, "performance": 79.89}}


def test_get_aram_augments_missing_id_is_just_absent_not_a_keyerror(monkeypatch):
    """Only tier-3+ augments come back with data - a caller asking about a
    lower-tier augment id must get a clean miss, not a crash."""
    text = (
        "class LolListAramAugments: data\n"
        "class Data: augments\n"
        "class Augment: id,name,tier,performance\n"
        "\n"
        'LolListAramAugments(Data([Augment(2132,"Warlock Juicebox",3,79.89)]))'
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        if json.get("method") == "initialize":
            return FakeResponse(headers={"Mcp-Session-Id": "sess-1"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse()
        if json.get("method") == "tools/call":
            return make_class_repr_tool_response(text)
        raise AssertionError(f"unexpected method: {json.get('method')}")

    import core.opgg_client as opgg_client_module

    monkeypatch.setattr(opgg_client_module.requests, "post", fake_post)

    client = OpggClient()
    result = client.get_aram_augments(81)

    assert result.get(9999) is None


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def make_tool_response(payload):
    return FakeResponse(json_data={"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}})


def test_get_lane_matchup_does_the_handshake_then_calls_the_tool(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        if json.get("method") == "initialize":
            return FakeResponse(headers={"Mcp-Session-Id": "sess-1"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse()
        if json.get("method") == "tools/call":
            return make_tool_response(
                {"data": {"lane_advantage_champion": "Darius", "recommended_play_style": "defensive", "opponent_champion_tip": "..."}}
            )
        raise AssertionError(f"unexpected method: {json.get('method')}")

    import core.opgg_client as opgg_client_module

    monkeypatch.setattr(opgg_client_module.requests, "post", fake_post)

    client = OpggClient()
    result = client.get_lane_matchup("Garen", "Darius", "top")

    assert result["lane_advantage_champion"] == "Darius"
    assert result["recommended_play_style"] == "defensive"

    tool_call = [c for c in calls if c[1].get("method") == "tools/call"][0]
    assert tool_call[1]["params"]["arguments"] == {"position": "top", "my_champion": "GAREN", "opponent_champion": "DARIUS"}
    assert tool_call[2]["Mcp-Session-Id"] == "sess-1"


def test_a_stale_session_is_reinitialized_once_and_retried(monkeypatch):
    call_methods = []

    def fake_post(url, json=None, headers=None, timeout=None):
        call_methods.append(json.get("method"))
        if json.get("method") == "initialize":
            return FakeResponse(headers={"Mcp-Session-Id": "sess-new"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse()
        if json.get("method") == "tools/call":
            # First tools/call fails (stale session); second (after
            # re-initializing) succeeds.
            if call_methods.count("tools/call") == 1:
                return FakeResponse(status_code=400)
            return make_tool_response({"data": {"lane_advantage_champion": "Garen"}})
        raise AssertionError(f"unexpected method: {json.get('method')}")

    import core.opgg_client as opgg_client_module

    monkeypatch.setattr(opgg_client_module.requests, "post", fake_post)

    client = OpggClient()
    client._session_id = "sess-stale"  # simulate an already-initialized client
    result = client.get_lane_matchup("Garen", "Darius", "top")

    assert result["lane_advantage_champion"] == "Garen"
    assert call_methods.count("initialize") == 1
    assert call_methods.count("tools/call") == 2


def test_an_mcp_tool_error_is_not_treated_as_a_stale_session(monkeypatch):
    """An OpggMcpError means the server understood the request and actively
    rejected it (e.g. an unknown champion key) - retrying after a fresh
    handshake would just get the same rejection, so it must not trigger
    the stale-session retry path.
    """
    call_methods = []

    def fake_post(url, json=None, headers=None, timeout=None):
        call_methods.append(json.get("method"))
        if json.get("method") == "initialize":
            return FakeResponse(headers={"Mcp-Session-Id": "sess-1"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse()
        if json.get("method") == "tools/call":
            return FakeResponse(
                json_data={"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "Invalid position or champion specified"}}
            )
        raise AssertionError(f"unexpected method: {json.get('method')}")

    import core.opgg_client as opgg_client_module

    monkeypatch.setattr(opgg_client_module.requests, "post", fake_post)

    client = OpggClient()
    with pytest.raises(OpggMcpError):
        client.get_lane_matchup("Notachampion", "Darius", "top")

    assert call_methods.count("tools/call") == 1
