import pytest
from fastapi.testclient import TestClient

import api.server as server


@pytest.fixture(scope="session")
def client():
    """Shared across every test file that needs the real HTTP app.

    Session-scoped, not per-test or per-module: `api.server.registry` is a
    real process-wide singleton built once at import time (like the actual
    packaged app), and exiting `TestClient(app)` runs FastAPI's lifespan
    shutdown - which calls `registry.stop_all()`, permanently shutting down
    its status thread pool (`ThreadPoolExecutor` has no restart). Any
    second `TestClient(app)` entered/exited elsewhere in the same test run
    - even in a different file - would shut it down again before this one's
    tests finish, crashing every later `GET /features` with "cannot
    schedule new futures after shutdown". Found live while adding the API
    integration test suite. One client for the whole session avoids it.
    """
    # Deliberately NOT used as a context manager: entering `with
    # TestClient(app)` drives the app's real lifespan, whose startup calls
    # registry.start_all() - spinning up all of its background polling
    # threads for the rest of the test session, which then pollutes
    # test_threaded_lifecycle.py's own `threading.enumerate()` counts (it
    # builds a separate registry and expects to be the only "camargo-*"
    # threads running). Plain instantiation skips lifespan entirely; routes
    # still work because `registry` itself is built eagerly at module
    # import time regardless of lifespan, not inside the startup hook.
    return TestClient(server.app)
