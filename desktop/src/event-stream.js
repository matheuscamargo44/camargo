const BASE_URL = window.camargo.backendUrl;
const WS_URL = BASE_URL.replace(/^http/, "ws") + "/ws/events";
// The token travels as a subprotocol because browsers cannot set headers on
// a WebSocket handshake.
const WS_PROTOCOLS = [window.camargo.wsSubprotocol, window.camargo.authToken];
const RECONNECT_DELAY_MS = 3000;

const eventSubscribers = new Set();

let ws = null;

function connect() {
  try {
    ws = new WebSocket(WS_URL, WS_PROTOCOLS);
  } catch {
    scheduleReconnect();
    return;
  }

  ws.onmessage = (event) => {
    try {
      pushEvent(JSON.parse(event.data));
    } catch {
      // ignore malformed messages
    }
  };

  ws.onclose = () => {
    ws = null;
    scheduleReconnect();
  };

  ws.onerror = () => {
    if (ws) ws.close();
  };
}

function scheduleReconnect() {
  setTimeout(connect, RECONNECT_DELAY_MS);
}

function pushEvent(data) {
  const entry = {
    level: data.level || "info",
    message: data.message || "",
    ts: data.ts || Date.now() / 1000,
  };

  for (const cb of eventSubscribers) cb(entry);
}

/**
 * Subscribe to incoming events. Callback receives { level, message, ts }.
 * Returns an unsubscribe function.
 */
export function onEvent(callback) {
  eventSubscribers.add(callback);
  return () => eventSubscribers.delete(callback);
}

/**
 * Starts the WebSocket connection. Call once at app bootstrap.
 */
export function startEventStream() {
  connect();
}
