import { fetchFeatureMeta, fetchFeatures, fetchHealth } from "./api.js";

const featureSubscribers = new Set();
const healthSubscribers = new Set();

let latestFeatures = {};
let latestHealth = { status: "unknown", league_connected: false, valorant_connected: false };
let featureMeta = [];

export function getFeatureMeta() {
  return featureMeta;
}

export function isLeagueConnected() {
  return Boolean(latestHealth && latestHealth.league_connected);
}

export function isValorantConnected() {
  return Boolean(latestHealth && latestHealth.valorant_connected);
}

/** Whichever client a feature belongs to is currently reachable. */
export function isFeatureConnected(game) {
  return game === "valorant" ? isValorantConnected() : isLeagueConnected();
}

export function onFeaturesUpdate(callback) {
  featureSubscribers.add(callback);
  callback(latestFeatures);
  return () => featureSubscribers.delete(callback);
}

export function onHealthUpdate(callback) {
  healthSubscribers.add(callback);
  callback(latestHealth);
  return () => healthSubscribers.delete(callback);
}

async function pollOnce() {
  try {
    // Metadata (title/category per feature) is static once loaded, so only
    // fetch it until it succeeds — everything else is polled every cycle.
    const requests = [fetchFeatures(), fetchHealth()];
    if (featureMeta.length === 0) requests.push(fetchFeatureMeta());

    const [features, health, meta] = await Promise.all(requests);
    latestFeatures = features;
    latestHealth = health;
    if (meta) featureMeta = meta;
  } catch (error) {
    latestHealth = { status: "offline", league_connected: false, valorant_connected: false };
  }
  for (const cb of featureSubscribers) cb(latestFeatures);
  for (const cb of healthSubscribers) cb(latestHealth);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Starts polling and resolves only once the backend has actually responded
 * (retrying for a while) so callers can render screens with real feature
 * metadata instead of racing the Electron-spawned backend's startup time.
 */
export async function startPolling(intervalMs = 4000) {
  const maxAttempts = 20; // ~20s of retries while the Python backend boots
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await pollOnce();
    if (featureMeta.length > 0) break;
    await wait(1000);
  }

  // Sequential, not setInterval: a stalled League client can hold /features
  // open for far longer than the interval, and overlapping polls would pile up.
  (async () => {
    for (;;) {
      await wait(intervalMs);
      await pollOnce();
    }
  })();
}

export function refreshNow() {
  return pollOnce();
}
