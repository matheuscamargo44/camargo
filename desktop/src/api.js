const BASE_URL = window.camargo.backendUrl;

export async function fetchHealth() {
  const response = await fetch(`${BASE_URL}/health`);
  if (!response.ok) throw new Error(`Backend unreachable (HTTP ${response.status})`);
  return response.json();
}

export async function fetchSummoner() {
  const response = await fetch(`${BASE_URL}/summoner`).catch(() => null);
  if (!response || !response.ok) return { connected: false };
  return response.json();
}

export async function fetchFeatureMeta() {
  const response = await fetch(`${BASE_URL}/features/meta`);
  if (!response.ok) throw new Error(`Failed to load feature metadata (HTTP ${response.status})`);
  return response.json();
}

export async function fetchFeatures() {
  const response = await fetch(`${BASE_URL}/features`);
  if (!response.ok) throw new Error(`Failed to load features (HTTP ${response.status})`);
  return response.json();
}

export async function toggleFeature(key) {
  const response = await fetch(`${BASE_URL}/features/${key}/toggle`, { method: "POST" });
  if (!response.ok) throw new Error(`Failed to toggle ${key} (HTTP ${response.status})`);
  return response.json();
}

export async function callAction(key, actionName, params = {}) {
  const response = await fetch(`${BASE_URL}/features/${key}/actions/${actionName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Failed to run ${actionName} on ${key} (HTTP ${response.status})`);
  }
  return data;
}
