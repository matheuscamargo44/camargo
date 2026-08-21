import asyncio
import inspect
import time
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.auth import TOKEN_HEADER, WS_SUBPROTOCOL, is_valid_token
from features.registry import FeatureRegistry

app = FastAPI(title="Camargo backend")

#: The renderer is loaded from file://, so its requests carry `Origin: null`.
#: Listing it explicitly (instead of "*") keeps an ordinary web page from
#: reading responses even if it somehow learned the token.
ALLOWED_ORIGINS = ["null"]


@app.middleware("http")
async def require_auth_token(request: Request, call_next):
    # Preflight carries no custom headers by definition; CORS answers it.
    if request.method == "OPTIONS":
        return await call_next(request)

    if not is_valid_token(request.headers.get(TOKEN_HEADER)):
        return JSONResponse({"detail": "Invalid or missing auth token"}, status_code=401)

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", TOKEN_HEADER],
)

_event_subscribers: list[WebSocket] = []
_event_loop: asyncio.AbstractEventLoop | None = None


def _on_event(level: str, message: str):
    event = {"level": level, "message": message, "ts": time.time()}
    if _event_loop is None:
        return
    for ws in list(_event_subscribers):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, event), _event_loop)


async def _safe_send(ws: WebSocket, event: dict):
    try:
        await ws.send_json(event)
    except Exception:
        if ws in _event_subscribers:
            _event_subscribers.remove(ws)


registry = FeatureRegistry(on_event=_on_event)

#: Lifecycle methods are not remotely callable, however public they look.
_RESERVED_ACTIONS = {"start", "stop", "get_status"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    registry.start_all()
    try:
        yield
    finally:
        registry.stop_all()


app.router.lifespan_context = lifespan


@app.get("/health")
def health():
    return {"status": "ok", "league_connected": registry.lcu.is_league_connected()}


@app.get("/summoner")
def get_summoner():
    if not registry.lcu.is_league_connected():
        return {"connected": False}
    try:
        res = registry.lcu.lcu_request("GET", "/lol-summoner/v1/current-summoner")
        if res.status_code == 200:
            data = res.json()
            ranked_tier = "UNRANKED"
            ranked_division = ""
            try:
                ranked_res = registry.lcu.lcu_request("GET", "/lol-ranked/v1/current-ranked-stats")
                if ranked_res.status_code == 200:
                    queues = ranked_res.json().get("queues", [])
                    solo = next((q for q in queues if q.get("queueType") == "RANKED_SOLO_5x5"), None)
                    if solo and solo.get("tier"):
                        ranked_tier = solo.get("tier", "UNRANKED")
                        ranked_division = solo.get("division", "")
            except Exception:
                pass

            return {
                "connected": True,
                "display_name": data.get("gameName") or data.get("displayName") or "",
                "tag_line": data.get("tagLine") or "",
                "summoner_level": data.get("summonerLevel", 1),
                "profile_icon_id": data.get("profileIconId", 1),
                "ranked_tier": ranked_tier,
                "ranked_division": ranked_division,
            }
    except Exception:
        pass
    return {"connected": False}


@app.get("/features")
def list_features():
    return registry.status()


@app.get("/features/meta")
def list_features_meta():
    return [
        {"key": feature.key, "title": feature.title, "category": feature.category}
        for feature in registry.features.values()
    ]


@app.post("/features/{key}/toggle")
def toggle_feature(key: str):
    if not registry.lcu.is_league_connected():
        raise HTTPException(status_code=503, detail="League client is not detected")

    try:
        feature = registry.get(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if hasattr(feature, "toggle"):
        feature.toggle()
    else:
        raise HTTPException(status_code=400, detail=f"'{key}' has no single toggle action")

    return feature.get_status()


@app.post("/features/{key}/actions/{action_name}")
def call_feature_action(key: str, action_name: str, params: dict = Body(default={})):
    """Generic dispatch for feature-specific actions (e.g. changing an icon,
    setting instalock champion). `params` keys must match the method's kwargs.
    """
    if not registry.lcu.is_league_connected():
        raise HTTPException(status_code=503, detail="League client is not detected")

    try:
        feature = registry.get(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if action_name.startswith("_") or action_name in _RESERVED_ACTIONS:
        raise HTTPException(status_code=404, detail=f"'{key}' has no action '{action_name}'")

    action = getattr(feature, action_name, None)
    if not callable(action) or not inspect.ismethod(action):
        raise HTTPException(status_code=404, detail=f"'{key}' has no action '{action_name}'")

    try:
        result = action(**params)
    except TypeError as exc:
        # Wrong or missing keys in `params` are a client mistake, not a crash
        raise HTTPException(status_code=400, detail=f"Invalid parameters for '{action_name}': {exc}")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"result": result, "status": feature.get_status()}


@app.websocket("/ws/events")
async def events(ws: WebSocket):
    # WebSockets are not covered by CORS: without these checks any web page
    # could subscribe to the event stream.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await ws.close(code=1008)
        return

    subprotocols = ws.scope.get("subprotocols") or []
    if len(subprotocols) < 2 or subprotocols[0] != WS_SUBPROTOCOL or not is_valid_token(subprotocols[1]):
        await ws.close(code=1008)
        return

    await ws.accept(subprotocol=WS_SUBPROTOCOL)
    _event_subscribers.append(ws)
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ws in _event_subscribers:
            _event_subscribers.remove(ws)
