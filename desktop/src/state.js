import { fetchFeatureMeta, fetchFeatures } from "./api.js";

const featureSubscribers = new Set();

let latestFeatures = {};
let featureMeta = [];

export function getFeatureMeta() {
  return featureMeta;
}

export function onFeaturesUpdate(callback) {
  featureSubscribers.add(callback);
  callback(latestFeatures);
  return () => featureSubscribers.delete(callback);
}

async function pollOnce() {
  try {
    // Metadata (title/category per feature) is static once loaded, so only
    // fetch it until it succeeds — everything else is polled every cycle.
    const requests = [fetchFeatures()];
    if (featureMeta.length === 0) requests.push(fetchFeatureMeta());

    const [features, meta] = await Promise.all(requests);
    latestFeatures = features;
    if (meta) featureMeta = meta;
  } catch (error) {
    // Backend may be briefly unreachable (still starting up, or restarting);
    // the next poll cycle retries automatically.
  }
  for (const cb of featureSubscribers) cb(latestFeatures);
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

  setInterval(pollOnce, intervalMs);
}

export function refreshNow() {
  return pollOnce();
}
