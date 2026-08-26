"""core.auth: the shared secret guarding the local HTTP API.

Security-focused unit coverage, separate from test_api_integration.py's
route-level auth checks (those verify the *effect*; these verify the
mechanism itself - constant-time comparison, empty-candidate handling,
where the token comes from).
"""
import hmac
import logging

import core.auth as auth_module


def test_valid_token_is_accepted():
    assert auth_module.is_valid_token(auth_module.AUTH_TOKEN) is True


def test_wrong_token_is_rejected():
    assert auth_module.is_valid_token("definitely-wrong") is False


def test_missing_token_is_rejected():
    assert auth_module.is_valid_token(None) is False


def test_empty_string_token_is_rejected():
    """An empty candidate must fail fast, not fall into hmac.compare_digest
    with a length mismatch that behaves correctly but for the wrong reason
    (compare_digest already handles it - this guards the explicit
    short-circuit staying in place regardless)."""
    assert auth_module.is_valid_token("") is False


def test_comparison_is_constant_time_not_a_plain_equality(monkeypatch):
    """A plain `==` comparison leaks the token one byte at a time via
    response-time differences (a classic timing attack). This must go
    through hmac.compare_digest, not Python's default string equality."""
    calls = []
    real_compare_digest = hmac.compare_digest

    def spy_compare_digest(a, b):
        calls.append((a, b))
        return real_compare_digest(a, b)

    monkeypatch.setattr(auth_module.hmac, "compare_digest", spy_compare_digest)

    auth_module.is_valid_token("some-candidate")

    assert calls == [("some-candidate", auth_module.AUTH_TOKEN)]


def test_resolve_token_prefers_the_environment_variable(monkeypatch):
    monkeypatch.setenv(auth_module.TOKEN_ENV_VAR, "  env-supplied-token  ")

    assert auth_module._resolve_token() == "env-supplied-token"


def test_resolve_token_generates_and_logs_one_when_unset(monkeypatch, caplog):
    monkeypatch.delenv(auth_module.TOKEN_ENV_VAR, raising=False)

    with caplog.at_level(logging.WARNING, logger="core.auth"):
        token = auth_module._resolve_token()

    assert len(token) > 20  # secrets.token_urlsafe(32) - not a trivial/short value
    assert token in caplog.text


# Deliberately no test reloads `core.auth` here: AUTH_TOKEN is a
# module-level singleton other test files capture via `from core.auth
# import AUTH_TOKEN` at their own import time, and every route test in the
# suite authenticates against it - reloading the module to exercise
# _resolve_token()'s caching would regenerate that value out from under
# them, an ordering-fragile trade not worth making for what
# test_resolve_token_prefers_the_environment_variable and
# test_resolve_token_generates_and_logs_one_when_unset already cover by
# calling _resolve_token() directly, without touching the live singleton.
