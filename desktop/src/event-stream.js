const BASE_URL = window.camargo.backendUrl;
const WS_URL = BASE_URL.replace(/^http/, "ws") + "/ws/events";
const MAX_EVENTS = 150;
const RECONNECT_DELAY_MS = 3000;

const eventSubscribers = new Set();
const eventBuffer = [];

let ws = null;
let shouldReconnect = true;

function connect() {
  try {
    ws = new WebSocket(WS_URL);
  } catch {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {};

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      pushEvent(data);
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
  if (!shouldReconnect) return;
  setTimeout(() => {
    if (shouldReconnect) connect();
  }, RECONNECT_DELAY_MS);
}

function pushEvent(data) {
  const entry = {
    level: data.level || "info",
    message: data.message || "",
    ts: data.ts || Date.now() / 1000,
  };

  eventBuffer.push(entry);
  if (eventBuffer.length > MAX_EVENTS) eventBuffer.shift();

  for (const cb of eventSubscribers) cb(entry, eventBuffer);
}

/**
 * Subscribe to incoming events. Callback receives (newEntry, allEntries).
 * Returns an unsubscribe function.
 */
export function onEvent(callback) {
  eventSubscribers.add(callback);
  return () => eventSubscribers.delete(callback);
}

/**
 * Returns the current event buffer (array of { level, message, ts }).
 */
export function getEventBuffer() {
  return eventBuffer;
}

/**
 * Starts the WebSocket connection. Call once at app bootstrap.
 */
export function startEventStream() {
  shouldReconnect = true;
  connect();
}

/**
 * Stops the WebSocket connection and prevents reconnects.
 */
export function stopEventStream() {
  shouldReconnect = false;
  if (ws) ws.close();
}
