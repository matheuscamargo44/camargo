from core.lcu_client import _headers, _service_url, _split_arg


def test_split_arg_extracts_value():
    assert _split_arg("--app-port=1234", "--app-port=") == "1234"


def test_split_arg_returns_none_when_prefix_missing():
    assert _split_arg("--other=1234", "--app-port=") is None


def test_service_url_none_without_port():
    assert _service_url(None) is None


def test_service_url_builds_local_https_url():
    assert _service_url("1234") == "https://127.0.0.1:1234"


def test_headers_empty_without_token():
    assert _headers(None) == {}


def test_headers_include_basic_auth():
    headers = _headers("secret")
    assert headers["Authorization"].startswith("Basic ")
    assert headers["Content-Type"] == "application/json"
