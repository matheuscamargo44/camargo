const BASE_URL = window.camargo.backendUrl;
const AUTH_HEADERS = { "X-Camargo-Token": window.camargo.authToken };
const JSON_HEADERS = { ...AUTH_HEADERS, "Content-Type": "application/json" };

export async function fetchHealth() {
  const response = await fetch(`${BASE_URL}/health`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Backend unreachable (HTTP ${response.status})`);
  return response.json();
}

export async function fetchSummoner() {
  const response = await fetch(`${BASE_URL}/summoner`, { headers: AUTH_HEADERS }).catch(() => null);
  if (!response || !response.ok) return { connected: false };
  return response.json();
}

export async function fetchFeatureMeta() {
  const response = await fetch(`${BASE_URL}/features/meta`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to load feature metadata (HTTP ${response.status})`);
  return response.json();
}

export async function fetchFeatures() {
  const response = await fetch(`${BASE_URL}/features`, { headers: AUTH_HEADERS });
  if (!response.ok) throw new Error(`Failed to load features (HTTP ${response.status})`);
  return response.json();
}

export async function toggleFeature(key) {
  const response = await fetch(`${BASE_URL}/features/${key}/toggle`, {
    method: "POST",
    headers: AUTH_HEADERS,
  });
  if (!response.ok) throw new Error(`Failed to toggle ${key} (HTTP ${response.status})`);
  return response.json();
}

export async function callAction(key, actionName, params = {}) {
  const response = await fetch(`${BASE_URL}/features/${key}/actions/${actionName}`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(params),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Failed to run ${actionName} on ${key} (HTTP ${response.status})`);
  }
  return data;
}
