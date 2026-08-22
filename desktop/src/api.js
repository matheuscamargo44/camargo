const BASE_URL = window.camargo.backendUrl;
const AUTH_HEADERS = { "X-Camargo-Token": window.camargo.authToken };
const JSON_HEADERS = { ...AUTH_HEADERS, "Content-Type": "application/json" };

// A hung TCP connection (no error, no response — not the same as a clean
// connection-refused) would otherwise block fetch() forever. The poll loop
// awaits each request in turn, so one stuck request would freeze all of the
// app's live data permanently instead of just failing that one cycle.
const DEFAULT_TIMEOUT_MS = 8000;

function fetchWithTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

export async function fetchHealth() {
  const response = await fetchWithTimeout(`${BASE_URL}/health`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Backend unreachable (HTTP ${response.status})`);
  return response.json();
}

export async function fetchSummoner() {
  const response = await fetchWithTimeout(`${BASE_URL}/summoner`, { headers: AUTH_HEADERS }).catch(() => null);
  if (!response || !response.ok) return { connected: false };
  return response.json();
}

export async function fetchFeatureMeta() {
  const response = await fetchWithTimeout(`${BASE_URL}/features/meta`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to load feature metadata (HTTP ${response.status})`);
  return response.json();
}

export async function fetchFeatures() {
  const response = await fetchWithTimeout(`${BASE_URL}/features`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to load features (HTTP ${response.status})`);
  return response.json();
}

export async function toggleFeature(key) {
  const response = await fetchWithTimeout(`${BASE_URL}/features/${key}/toggle`, {
    method: "POST",
    headers: AUTH_HEADERS,
  });
  if (!response.ok) throw new Error(`Failed to toggle ${key} (HTTP ${response.status})`);
  return response.json();
}

export async function callAction(key, actionName, params = {}) {
  // Some actions (bulk disenchant, mass invites) legitimately run longer
  // than the default budget, so they get more room before being aborted.
  const response = await fetchWithTimeout(
    `${BASE_URL}/features/${key}/actions/${actionName}`,
    { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(params) },
    20000
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Failed to run ${actionName} on ${key} (HTTP ${response.status})`);
  }
  return data;
}

export async function fetchLogs(after = 0) {
  const response = await fetchWithTimeout(`${BASE_URL}/logs?after=${after}`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to load logs (HTTP ${response.status})`);
  return response.json();
}

export async function clearLogs() {
  const response = await fetchWithTimeout(`${BASE_URL}/logs`, { method: "DELETE", headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to clear logs (HTTP ${response.status})`);
  return response.json();
}

/**
 * Forwards a renderer-side failure to the backend log, so one copy of the
 * activity log covers both processes.
 */
export function reportClientError(message, detail, source = "renderer") {
  return fetchWithTimeout(`${BASE_URL}/logs/client`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ level: "ERROR", message: String(message), detail, source }),
  }).catch(() => {
    // The backend being unreachable is itself the failure being reported.
  });
}
