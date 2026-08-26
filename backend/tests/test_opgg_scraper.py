"""opgg_scraper: reading OP.GG's own ARAM: Mayhem augment page.

The page's real payload is a Next.js React Server Component chunk, so
these fixtures reproduce that literal escaped-JSON shape (captured live
from a real page fetch) rather than plain JSON, to actually exercise the
regex against the format the site serves.
"""
import requests

from core.opgg_scraper import scrape_aram_augments


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


#: A trimmed real fragment of the embedded payload (see module docstring
#: of core.opgg_scraper) - two augments, one tier-0 (best) and one tier-5
#: (the noisy catch-all), each with the trailing name/icon/rarity/desc
#: fields a real entry also carries, to prove those don't break the match.
_SAMPLE_CHUNK = (
    r'self.__next_f.push([1,"52:[{\"id\":1320,\"tier\":0,\"performance\":81.43,\"popular\":5.12,'
    r'\"name\":\"Upgrade Collector\",\"key\":\"ARAM_Upgrade_Collector\",\"rarity\":1,'
    r'\"desc\":\"Executing enemies with The Collector\'s Passive.\"},'
    r'{\"id\":2007,\"tier\":5,\"performance\":170.0,\"popular\":0.0,'
    r'\"name\":\"Devil on Your Shoulder\",\"key\":\"Devil\",\"rarity\":8,'
    r'\"desc\":\"Something else entirely.\"}]"])'
)


def test_scrapes_every_augment_including_the_worst_tier(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: _FakeResponse(_SAMPLE_CHUNK))

    data = scrape_aram_augments("Viego")

    assert data == {
        1320: {"id": 1320, "tier": 0, "performance": 81.43},
        2007: {"id": 2007, "tier": 5, "performance": 170.0},
    }


def test_url_uses_the_lowercased_alias(monkeypatch):
    captured = {}

    def fake_get(url, timeout, headers):
        captured["url"] = url
        return _FakeResponse(_SAMPLE_CHUNK)

    monkeypatch.setattr(requests, "get", fake_get)

    scrape_aram_augments("MonkeyKing")

    assert captured["url"] == "https://op.gg/lol/modes/aram-mayhem/monkeyking/augments"


def test_network_failure_degrades_to_empty(monkeypatch):
    def raise_error(url, timeout, headers):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(requests, "get", raise_error)

    assert scrape_aram_augments("Viego") == {}


def test_http_error_status_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: _FakeResponse("", status_code=404))

    assert scrape_aram_augments("UnknownChampion") == {}


def test_a_page_with_no_recognizable_payload_degrades_to_empty(monkeypatch):
    """OP.GG rebuilding their frontend and changing this internal, undocumented
    shape must never raise - just come back with nothing, like every other
    data source in this app."""
    monkeypatch.setattr(requests, "get", lambda url, timeout, headers: _FakeResponse("<html>totally different page</html>"))

    assert scrape_aram_augments("Viego") == {}
