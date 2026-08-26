"""A fake League Client (LCU) HTTP server, for end-to-end tests that need
the real feature code, the real background polling threads, and a real
`core.lcu_client.LCUClient` making real HTTP calls - without League itself
installed anywhere.

Scope, deliberately: this implements the subset of the real LCU REST API
that `backend/features/*.py` actually calls, for the flows covered by
`test_e2e_scenarios.py` (Instalock, AutoBan, AutoHonor, AutoPlayAgain,
AramBenchSwap). It is not a full LCU emulator - extending it to a new
feature means adding that feature's endpoints to `_build_app()` below, the
same way the existing ones were added.

Not HTTPS: the real LCU serves HTTPS with a self-signed cert, which
`LCUClient` already treats as untrusted (`verify=False`) - the scheme
itself carries no behavior under test, so this serves plain HTTP and the
test fixture in test_e2e_scenarios.py points the client at it via
`http://`, avoiding the ceremony of a throwaway TLS cert for zero benefit.
"""
import copy
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

#: A minimal but real-shaped roster - just enough champions for the E2E
#: scenarios to build priority lists and bans/locks against.
DEFAULT_CHAMPIONS = [
    {"id": 103, "name": "Ahri", "alias": "Ahri"},
    {"id": 157, "name": "Yasuo", "alias": "Yasuo"},
    {"id": 99, "name": "Lux", "alias": "Lux"},
    {"id": 115, "name": "Ziggs", "alias": "Ziggs"},
    {"id": 86, "name": "Garen", "alias": "Garen"},
    {"id": 1, "name": "Annie", "alias": "Annie"},
]


class FakeLeagueState:
    """Mutable game state the fake server reads/writes, plus a request log
    E2E tests assert against instead of a mocked function call - the
    assertion is "the real LCUClient sent this real HTTP request", not
    "this Python function was called with these arguments"."""

    def __init__(self):
        self.gameflow_phase = "None"
        self.champ_select_session = None  # dict, or None -> 404 "RPC_ERROR"
        self.lobby = None
        self.honor_ballot = None
        self.summoner = {
            "summonerId": 1,
            "puuid": "local-puuid",
            "gameName": "TestSummoner",
            "tagLine": "NA1",
            "summonerLevel": 30,
            "profileIconId": 1,
        }
        self.champions = copy.deepcopy(DEFAULT_CHAMPIONS)
        self.requests = []  # [{"method", "path", "body"}], oldest first

    def log(self, method, path, body):
        self.requests.append({"method": method, "path": path, "body": body})

    def requests_to(self, path_prefix, method=None):
        return [
            r
            for r in self.requests
            if r["path"].startswith(path_prefix) and (method is None or r["method"] == method)
        ]

    # -- scenario helpers: build a champ-select session in one call --

    def open_champ_select(self, my_team, their_team=None, bans=None, bench=None, local_cell_id=0):
        """`my_team`/`their_team` are lists of {"cellId", "championId",
        "assignedPosition"}. One entry in `my_team` should have an
        unfinished pick action for the local player if you want
        Instalock/AutoBan to have something to act on - use
        `add_pending_action` for that.
        """
        self.gameflow_phase = "ChampSelect"
        self.champ_select_session = {
            "localPlayerCellId": local_cell_id,
            "myTeam": my_team,
            "theirTeam": their_team or [],
            "bans": bans or {"myTeamBans": [], "theirTeamBans": []},
            "benchChampions": bench or [],
            "actions": [[]],
        }

    def add_pending_action(self, action_id, cell_id, action_type="pick"):
        self.champ_select_session["actions"][0].append(
            {"id": action_id, "actorCellId": cell_id, "type": action_type, "completed": False}
        )

    def end_champ_select(self):
        self.champ_select_session = None
        self.gameflow_phase = "InProgress"


def _build_app(state: FakeLeagueState) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def log_and_serve(request: Request, call_next):
        body = None
        raw = await request.body()
        if raw:
            try:
                import json

                body = json.loads(raw)
            except Exception:
                body = raw.decode("utf-8", errors="replace")
        state.log(request.method, request.url.path, body)
        # Body was already consumed above; rebuild the receive channel so
        # the route handler (which reads request.json() again) still works.
        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        request._receive = receive
        return await call_next(request)

    @app.get("/lol-summoner/v1/current-summoner")
    def current_summoner():
        return state.summoner

    @app.get("/lol-gameflow/v1/gameflow-phase")
    def gameflow_phase():
        return state.gameflow_phase

    @app.get("/lol-gameflow/v1/session")
    def gameflow_session():
        return {"gameData": {"queue": {"id": 420}}}

    @app.get("/lol-champ-select/v1/session")
    def champ_select_session():
        if state.champ_select_session is None:
            # Real LCU 404s with an RPC_ERROR body when there's no active
            # session - features check for that literal substring.
            return PlainTextResponse('{"errorCode":"RPC_ERROR"}', status_code=404)
        return state.champ_select_session

    @app.patch("/lol-champ-select/v1/session/actions/{action_id}")
    async def complete_action(action_id: int, request: Request):
        payload = await request.json()
        for phase in state.champ_select_session.get("actions", []):
            for action in phase:
                if action["id"] == action_id:
                    action["completed"] = payload.get("completed", True)
                    action["championId"] = payload.get("championId")
                    return PlainTextResponse("", status_code=204)
        return PlainTextResponse("", status_code=404)

    @app.post("/lol-champ-select/v1/session/bench/swap/{champion_id}")
    def bench_swap(champion_id: int):
        bench = state.champ_select_session.get("benchChampions", [])
        swapped_out = next(
            (p.get("championId") for p in state.champ_select_session["myTeam"] if p.get("cellId") == state.champ_select_session["localPlayerCellId"]),
            None,
        )
        for p in state.champ_select_session["myTeam"]:
            if p.get("cellId") == state.champ_select_session["localPlayerCellId"]:
                p["championId"] = champion_id
        state.champ_select_session["benchChampions"] = [
            b for b in bench if b.get("championId") != champion_id
        ] + ([{"championId": swapped_out}] if swapped_out else [])
        return PlainTextResponse("", status_code=204)

    @app.get("/lol-game-data/assets/v1/champion-summary.json")
    def champion_summary():
        return state.champions

    @app.get("/lol-lobby/v2/lobby")
    def lobby():
        if state.lobby is None:
            return JSONResponse({}, status_code=404)
        return state.lobby

    @app.post("/lol-lobby/v2/play-again")
    def play_again():
        return PlainTextResponse("", status_code=204)

    @app.post("/lol-lobby/v2/lobby/matchmaking/search")
    def matchmaking_search():
        return PlainTextResponse("", status_code=204)

    @app.get("/lol-honor-v2/v1/ballot")
    def honor_ballot():
        if state.honor_ballot is None:
            return JSONResponse({}, status_code=404)
        return state.honor_ballot

    @app.post("/lol-honor-v2/v1/honor-player")
    def honor_player():
        return PlainTextResponse("", status_code=204)

    return app


class RunningFakeServer:
    def __init__(self, state, port, thread, uvicorn_server):
        self.state = state
        self.port = port
        self._thread = thread
        self._uvicorn_server = uvicorn_server

    def stop(self):
        self._uvicorn_server.should_exit = True
        self._thread.join(timeout=5.0)


def start_fake_lcu_server() -> RunningFakeServer:
    """Starts the fake server on an OS-assigned free port, in a background
    thread, and waits for it to actually be accepting connections before
    returning - so the first request a test makes doesn't race the
    server's own startup.
    """
    state = FakeLeagueState()
    app = _build_app(state)
    # log_config=None: uvicorn's default startup otherwise calls
    # logging.config.dictConfig(), which resets the root logger's handlers
    # and the "uvicorn.access" logger's level - undoing what
    # core.activity_log.install() already set up in this same process and
    # breaking test_activity_log.py's assertions about it. Found live by
    # running the whole suite together, not just this file in isolation.
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", log_config=None)
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5.0
    while not getattr(server, "started", False):
        if time.monotonic() > deadline:
            raise RuntimeError("fake LCU server did not start in time")
        time.sleep(0.01)

    port = server.servers[0].sockets[0].getsockname()[1]

    # uvicorn's own startup reconfigures the "uvicorn.access" logger's level
    # to match `log_level` above regardless of `log_config=None` - which
    # undoes core.activity_log.install()'s own setup (already run once, at
    # api.server import time) in this same process. Re-running it is
    # idempotent (it only adds its handlers if they aren't already present)
    # and simply re-applies the level it wants - found live by running the
    # whole suite together, not just this file in isolation.
    from core.activity_log import install as install_activity_log

    install_activity_log()

    return RunningFakeServer(state, port, thread, server)
