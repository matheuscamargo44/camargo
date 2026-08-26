"""End-to-end HTTP contract for the whole backend API, walked through the
real FastAPI app and the real feature registry (no live League/VALORANT
client needed - the registry's own "not connected" state is exactly what a
freshly-launched backend looks like, which is what these tests exercise).

Complements the feature-level unit tests: those call feature methods
directly and never touch auth, routing, reserved-action blocking, or the
`params` -> method-kwargs bridge that only exists at this HTTP layer.
"""
import pytest

import api.server as server
from core.auth import AUTH_TOKEN, TOKEN_HEADER

AUTH = {TOKEN_HEADER: AUTH_TOKEN}

# `client` comes from tests/conftest.py - session-scoped, shared with every
# other test file that needs the real HTTP app. See its docstring for why
# it must not be created per-test/per-module here.


@pytest.fixture(scope="module", autouse=True)
def isolated_config(tmp_path_factory):
    """A couple of tests below legitimately reach save_config (toggling a
    feature through the real HTTP path) - redirected to a throwaway file so
    nothing here ever writes to the real dev-mode config.json. save_config
    re-reads CONFIG_PATH at call time, so patching the module attribute is
    enough even though `registry` (built at import time, before this
    fixture runs) already loaded the real one into memory - that initial
    read is harmless, only a later write would not be.
    """
    import core.config as config_module

    original_path = config_module.CONFIG_PATH
    config_module.CONFIG_PATH = tmp_path_factory.mktemp("api-integration") / "config.json"
    yield
    config_module.CONFIG_PATH = original_path


@pytest.fixture
def connected(monkeypatch):
    """Bypasses `_require_connected` for both games, the way a real running
    League/VALORANT client would - needed to reach an action's own
    parameter handling rather than stopping at the 503 gate."""
    monkeypatch.setattr(server.registry.lcu, "is_league_connected", lambda: True)
    monkeypatch.setattr(server.registry.valorant, "is_connected", lambda: True)


@pytest.fixture
def disconnected(monkeypatch):
    """The 503 gate's own test needs a *guaranteed* absent client. This used
    to rely on there simply being no League running wherever the suite
    happened to execute - which silently inverts into a failure the moment a
    developer runs the tests with the game open, exactly the environment
    where the rest of the suite is most likely to be run.
    """
    monkeypatch.setattr(server.registry.lcu, "is_league_connected", lambda: False)
    monkeypatch.setattr(server.registry.valorant, "is_connected", lambda: False)


# -- auth: every route, every method --


ROUTES = [
    ("GET", "/health"),
    ("GET", "/summoner"),
    ("GET", "/features"),
    ("GET", "/features/meta"),
    ("GET", "/features/auto_accept"),
    ("POST", "/features/auto_accept/toggle"),
    ("POST", "/features/auto_accept/actions/toggle"),
    ("GET", "/logs"),
    ("POST", "/logs/client"),
    ("DELETE", "/logs"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_route_requires_a_valid_token(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert client.request(method, path, headers=AUTH).status_code != 401


def test_a_preflight_request_is_never_blocked_by_the_auth_middleware(client):
    # No token at all - CORSMiddleware answers this, the auth middleware
    # must let it through unconditionally (see server.py's own comment).
    response = client.options(
        "/features",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code != 401


def test_an_empty_token_header_is_rejected_like_a_missing_one(client):
    assert client.get("/health", headers={TOKEN_HEADER: ""}).status_code == 401


# -- route wiring / contract --


def test_features_lists_every_registered_feature_keyed_by_its_own_key(client):
    body = client.get("/features", headers=AUTH).json()

    assert set(body.keys()) == set(server.registry.features.keys())
    for key, status in body.items():
        assert status.get("key") == key


def test_features_meta_covers_every_registered_feature(client):
    body = client.get("/features/meta", headers=AUTH).json()

    keys = {entry["key"] for entry in body}
    assert keys == set(server.registry.features.keys())
    for entry in body:
        assert entry["title"]
        assert entry["category"]
        assert entry["game"] in ("league", "valorant")


def test_unknown_feature_key_is_a_404_everywhere(client):
    assert client.get("/features/not_a_real_feature", headers=AUTH).status_code == 404
    assert client.post("/features/not_a_real_feature/toggle", headers=AUTH).status_code == 404
    assert (
        client.post("/features/not_a_real_feature/actions/whatever", headers=AUTH, json={}).status_code == 404
    )


@pytest.mark.parametrize("action_name", ["start", "stop", "get_status", "_reset_game_state"])
def test_lifecycle_and_private_methods_are_never_remotely_callable(client, connected, action_name):
    """Every feature has these; if even one were reachable, an external
    caller could restart/kill a feature's background thread on demand."""
    response = client.post(
        f"/features/auto_accept/actions/{action_name}", headers=AUTH, json={}
    )
    assert response.status_code == 404


def test_an_unconnected_feature_gates_its_toggle_and_actions_with_503(client, disconnected):
    assert client.post("/features/instalock/toggle", headers=AUTH).status_code == 503
    response = client.post(
        "/features/instalock/actions/add_champion", headers=AUTH, json={"champion_name": "Ahri"}
    )
    assert response.status_code == 503


def test_a_feature_with_no_toggle_method_reports_400_not_a_crash(client, connected):
    # mass_disenchant (MassDisenchant) exposes actions but no toggle().
    response = client.post("/features/mass_disenchant/toggle", headers=AUTH)
    assert response.status_code == 400


# -- params -> method kwargs: type safety at the HTTP boundary --


def test_wrong_typed_param_is_rejected_before_it_reaches_the_feature(client, connected):
    """The bug this guards: toggle(self, state: bool = None) assigns
    `state` verbatim whenever it isn't None - a dict landing there used to
    flow straight through Python's dynamic typing and get persisted into
    config.json's "enabled" field as a raw object."""
    feature = server.registry.get("auto_honor")
    original_enabled = feature.config.get("auto_honor", {}).get("enabled")

    response = client.post(
        "/features/auto_honor/actions/toggle", headers=AUTH, json={"state": {"a": 1}}
    )

    assert response.status_code == 400
    assert feature.config.get("auto_honor", {}).get("enabled") == original_enabled


def test_a_correctly_typed_param_still_works(client, connected):
    feature = server.registry.get("auto_honor")
    previous = feature.config.get("auto_honor", {}).get("enabled")
    try:
        response = client.post(
            "/features/auto_honor/actions/toggle", headers=AUTH, json={"state": True}
        )
        assert response.status_code == 200
        assert feature.config["auto_honor"]["enabled"] is True
    finally:
        # `registry` is a real process-wide singleton shared with every
        # other test module - restore it rather than leak state sideways.
        feature.toggle(bool(previous))


def test_a_string_param_rejects_a_non_string_value(client, connected):
    response = client.post(
        "/features/auto_party_invite/actions/set_summoners", headers=AUTH, json={"summoners": 12345}
    )
    assert response.status_code == 400


def test_a_missing_required_param_is_a_400_not_a_500(client, connected):
    response = client.post("/features/instalock/actions/add_champion", headers=AUTH, json={})
    assert response.status_code == 400


# -- /logs: the client-error intake --


def test_client_log_requires_a_non_empty_message(client):
    response = client.post("/logs/client", headers=AUTH, json={"message": ""})
    assert response.status_code == 400


def test_client_log_accepts_a_normal_error_report(client):
    response = client.post(
        "/logs/client", headers=AUTH, json={"level": "ERROR", "message": "boom", "source": "renderer"}
    )
    assert response.status_code == 200


def test_client_log_falls_back_to_error_for_an_unknown_level(client):
    response = client.post(
        "/logs/client", headers=AUTH, json={"level": "NOT_A_REAL_LEVEL", "message": "boom"}
    )
    assert response.status_code == 200
