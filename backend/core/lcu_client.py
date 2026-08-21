"""Thin HTTP client for the League Client Update (LCU) and Riot client local APIs.

Credentials are discovered by reading the command line of the running
LeagueClientUx.exe process. No feature/business logic lives here.
"""
import base64
import json
import logging
import threading
import time

import psutil
import requests
import urllib3

urllib3.disable_warnings()

REQUEST_TIMEOUT_SECONDS = 5
REQUEST_RETRIES = 2
#: Discovering credentials means walking every process on the machine and
#: reading its command line (~16ms with 250 processes). Nine feature loops plus
#: the /features poll used to pay that cost several times a second, so results
#: are reused for a moment. A failed request still forces an immediate rescan,
#: which is what actually matters when the client restarts on a new port.
CREDENTIAL_TTL_SECONDS = 5.0


def _split_arg(arg, prefix):
    if arg and arg.startswith(prefix):
        return arg.split("=", 1)[1]
    return None


def find_league_client_credentials():
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                name = info.get("name") or ""
                if name.lower() != "leagueclientux.exe":
                    continue

                port = None
                token = None
                for arg in info.get("cmdline") or []:
                    port = port or _split_arg(arg, "--app-port=")
                    token = token or _split_arg(arg, "--remoting-auth-token=")

                if port and token:
                    return port, token
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        logger.exception("find_league_client_credentials failed")

    return None, None


def find_riot_client_credentials():
    try:
        for process in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                info = process.info
                name = info.get("name") or ""
                if "leagueclientux" not in name.lower():
                    continue

                port = None
                token = None
                for arg in info.get("cmdline") or []:
                    token = token or _split_arg(arg, "--riotclient-auth-token=")
                    port = port or _split_arg(arg, "--riotclient-app-port=")

                if port and token:
                    return port, token
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        logger.exception("find_riot_client_credentials failed")

    return None, None


def _service_url(port):
    return f"https://127.0.0.1:{port}" if port else None


def _headers(token):
    if not token:
        return {}
    auth = base64.b64encode(f"riot:{token}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


logger = logging.getLogger(__name__)


class LCUClient:
    """Single shared connection to the League/Riot local APIs.

    Meant to be instantiated once and injected into every feature, instead
    of each feature creating its own connection (as the original tool did).
    """

    def __init__(self):
        # Every feature loop shares this instance across threads.
        self._lock = threading.RLock()
        self.league_port = None
        self.league_token = None
        self.league_url = None
        self.league_headers = {}
        self._league_scanned_at = 0.0
        self.riot_port = None
        self.riot_token = None
        self.riot_url = None
        self.riot_headers = {}
        self.update_league_credentials()
        self.update_riot_credentials()

    def update_league_credentials(self):
        """Rescan for League credentials, ignoring the cache."""
        port, token = find_league_client_credentials()
        with self._lock:
            self.league_port = port
            self.league_token = token
            self.league_url = _service_url(port)
            self.league_headers = _headers(token)
            self._league_scanned_at = time.monotonic()

    def update_riot_credentials(self):
        """Rescan for Riot client credentials, ignoring the cache."""
        port, token = find_riot_client_credentials()
        with self._lock:
            self.riot_port = port
            self.riot_token = token
            self.riot_url = _service_url(port)
            self.riot_headers = _headers(token)

    def _refresh_league_if_stale(self):
        with self._lock:
            fresh = time.monotonic() - self._league_scanned_at < CREDENTIAL_TTL_SECONDS
            if fresh:
                return
            self.update_league_credentials()

    def is_league_connected(self):
        self._refresh_league_if_stale()
        return bool(self.league_url)

    def _service_connection(self, service):
        with self._lock:
            if service == "league":
                return self.league_url, self.league_headers
            return self.riot_url, self.riot_headers

    def _request(self, method, base_url, headers, endpoint, body, refresh_credentials, service):
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError("Invalid method")

        payload = None if body == "" else body
        if payload is not None:
            payload = json.dumps(payload)

        for attempt in range(REQUEST_RETRIES + 1):
            if not base_url:
                refresh_credentials()
                base_url, headers = self._service_connection(service)
                if not base_url:
                    raise RuntimeError(f"Could not find {service} client credentials")

            try:
                response = requests.request(
                    method,
                    f"{base_url}{endpoint}",
                    headers=headers,
                    data=payload,
                    verify=False,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.exceptions.RequestException as exc:
                if attempt == REQUEST_RETRIES:
                    logger.error(
                        "%s %s %s failed after %d attempts: %s",
                        service, method, endpoint, attempt + 1, exc,
                    )
                    raise
                logger.debug(
                    "%s %s %s failed (attempt %d), rescanning credentials: %s",
                    service, method, endpoint, attempt + 1, exc,
                )
                refresh_credentials()
                base_url, headers = self._service_connection(service)
            else:
                # A 404 is how the LCU says "not in that state right now"
                # (no champ select, no ballot, no lobby): routine, not a fault.
                if response.status_code >= 400 and response.status_code != 404:
                    logger.warning(
                        "%s %s %s -> HTTP %d: %s",
                        service, method, endpoint, response.status_code,
                        response.text[:300].replace(chr(10), " "),
                    )
                else:
                    logger.debug("%s %s %s -> HTTP %d", service, method, endpoint, response.status_code)
                return response

    def lcu_request(self, method, endpoint, body=""):
        return self._request(
            method,
            self.league_url,
            self.league_headers,
            endpoint,
            body,
            self.update_league_credentials,
            "league",
        )

    def riot_request(self, method, endpoint, body=""):
        return self._request(
            method,
            self.riot_url,
            self.riot_headers,
            endpoint,
            body,
            self.update_riot_credentials,
            "riot",
        )
