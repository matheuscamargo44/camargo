"""Thin HTTP client for the League Client Update (LCU) and Riot client local APIs.

Credentials are discovered by reading the command line of the running
LeagueClientUx.exe process. No feature/business logic lives here.
"""
import base64
import json

import psutil
import requests
import urllib3

urllib3.disable_warnings()

REQUEST_TIMEOUT_SECONDS = 5
REQUEST_RETRIES = 2


def _split_arg(arg, prefix):
    if arg and arg.startswith(prefix):
        return arg.split("=", 1)[1]
    return None


def find_league_client_credentials():
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        info = proc.info
        if info.get("name") != "LeagueClientUx.exe":
            continue

        port = None
        token = None
        for arg in info.get("cmdline") or []:
            port = port or _split_arg(arg, "--app-port=")
            token = token or _split_arg(arg, "--remoting-auth-token=")

        if port and token:
            return port, token

    return None, None


def find_riot_client_credentials():
    for process in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        info = process.info
        name = info.get("name") or ""
        if "LeagueClientUx" not in name:
            continue

        port = None
        token = None
        for arg in info.get("cmdline") or []:
            token = token or _split_arg(arg, "--riotclient-auth-token=")
            port = port or _split_arg(arg, "--riotclient-app-port=")

        if port and token:
            return port, token

    return None, None


def _service_url(port):
    return f"https://127.0.0.1:{port}" if port else None


def _headers(token):
    if not token:
        return {}
    auth = base64.b64encode(f"riot:{token}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


class LCUClient:
    """Single shared connection to the League/Riot local APIs.

    Meant to be instantiated once and injected into every feature, instead
    of each feature creating its own connection (as the original tool did).
    """

    def __init__(self):
        self.update_league_credentials()
        self.update_riot_credentials()

    def update_league_credentials(self):
        self.league_port, self.league_token = find_league_client_credentials()
        self.league_url = _service_url(self.league_port)
        self.league_headers = _headers(self.league_token)

    def update_riot_credentials(self):
        self.riot_port, self.riot_token = find_riot_client_credentials()
        self.riot_url = _service_url(self.riot_port)
        self.riot_headers = _headers(self.riot_token)

    def is_league_connected(self):
        return bool(self.league_url)

    def _service_connection(self, service):
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
                return requests.request(
                    method,
                    f"{base_url}{endpoint}",
                    headers=headers,
                    data=payload,
                    verify=False,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.exceptions.RequestException:
                if attempt == REQUEST_RETRIES:
                    raise
                refresh_credentials()
                base_url, headers = self._service_connection(service)

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
