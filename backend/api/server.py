import inspect
import logging
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.activity_log import ACTIVITY_LOG, RENDERER_LOGGER
from core.activity_log import install as install_activity_log
from core.auth import TOKEN_HEADER, is_valid_token
from features.registry import FeatureRegistry

logger = logging.getLogger(__name__)

# Installed before the registry is built so feature construction is captured.
install_activity_log()

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
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", TOKEN_HEADER],
)

LOG_LEVELS = {"success": logging.INFO, "info": logging.INFO, "warn": logging.WARNING}


def _on_event(level: str, message: str):
    """Features report what they did here.

    The UI deliberately shows no notifications, so these go to the log
    instead of over the wire.
    """
    logger.log(LOG_LEVELS.get(level, logging.INFO), "[%s] %s", level, message)


registry = FeatureRegistry(on_event=_on_event)

#: Lifecycle methods are not remotely callable, however public they look.
_RESERVED_ACTIONS = {"start", "stop", "get_status"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    registry.start_all()
    try:
        yield
    finally:
        registry.stop_all()


app.router.lifespan_context = lifespan


VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
MAX_CLIENT_MESSAGE = 4000


@app.get("/logs")
def read_logs(after: int = 0, limit: int = 750):
    """Entries newer than `after`, so the UI can poll incrementally."""
    entries = ACTIVITY_LOG.entries(after=after, limit=max(1, min(limit, 750)))
    return {
        "entries": entries,
        "next": entries[-1]["seq"] if entries else after,
    }


@app.post("/logs/client")
def write_client_log(payload: dict = Body(default={})):
    """Errors raised in the renderer, so one copy of the log has both sides."""
    message = str(payload.get("message", "")).strip()[:MAX_CLIENT_MESSAGE]
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    level = str(payload.get("level", "ERROR")).upper()
    if level not in VALID_LOG_LEVELS:
        level = "ERROR"

    detail = payload.get("detail")
    if detail is not None:
        detail = str(detail)[:MAX_CLIENT_MESSAGE]

    source = str(payload.get("source", "")).strip() or RENDERER_LOGGER
    ACTIVITY_LOG.record(level, message, source=f"{RENDERER_LOGGER}.{source}"[:80], detail=detail)
    return {"ok": True}


@app.delete("/logs")
def clear_logs():
    ACTIVITY_LOG.clear()
    logger.info("Activity log cleared")
    return {"ok": True}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "league_connected": registry.lcu.is_league_connected(),
        "valorant_connected": registry.valorant.is_connected(),
    }


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
                logger.exception("get_summoner failed")

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
        logger.exception("get_summoner failed")
    return {"connected": False}


@app.get("/features")
def list_features():
    return registry.status()


@app.get("/features/meta")
def list_features_meta():
    return [
        {"key": feature.key, "title": feature.title, "category": feature.category, "game": feature.game}
        for feature in registry.features.values()
    ]


def _require_connected(feature):
    if registry.is_connected(feature):
        return
    label = "VALORANT" if feature.game == "valorant" else "League"
    raise HTTPException(status_code=503, detail=f"{label} client is not detected")


@app.post("/features/{key}/toggle")
def toggle_feature(key: str):
    try:
        feature = registry.get(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    _require_connected(feature)

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
    try:
        feature = registry.get(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    _require_connected(feature)

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
