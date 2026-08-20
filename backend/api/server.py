import asyncio
import time

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from features.registry import FeatureRegistry

app = FastAPI(title="Camargo backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.on_event("startup")
async def startup():
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    registry.start_all()


@app.on_event("shutdown")
async def shutdown():
    registry.stop_all()


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

    action = getattr(feature, action_name, None)
    if action is None or action_name.startswith("_") or not callable(action):
        raise HTTPException(status_code=404, detail=f"'{key}' has no action '{action_name}'")

    try:
        result = action(**params)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"result": result, "status": feature.get_status()}


@app.websocket("/ws/events")
async def events(ws: WebSocket):
    await ws.accept()
    _event_subscribers.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in _event_subscribers:
            _event_subscribers.remove(ws)
