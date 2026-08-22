import { fetchFeatureMeta, fetchFeatures, fetchHealth } from "./api.js";

const featureSubscribers = new Set();
const healthSubscribers = new Set();
const metaSubscribers = new Set();

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

/**
 * Feature metadata arriving (possibly well after the app first rendered, if
 * the backend was slow to start). Screens built before that point need this
 * to redraw themselves instead of staying stuck on an empty state forever.
 */
export function onFeatureMetaUpdate(callback) {
  metaSubscribers.add(callback);
  if (featureMeta.length > 0) callback(featureMeta);
  return () => metaSubscribers.delete(callback);
}

async function pollOnce() {
  // allSettled, not all: one endpoint timing out (see api.js) must not throw
  // away results the others already got back. A previous version used
  // Promise.all here, so a single flaky request could leave the whole app
  // stuck showing stale/empty data even while everything else kept working.
  const needsMeta = featureMeta.length === 0;
  const requests = [fetchFeatures(), fetchHealth()];
  if (needsMeta) requests.push(fetchFeatureMeta());

  const [featuresResult, healthResult, metaResult] = await Promise.allSettled(requests);

  if (featuresResult.status === "fulfilled") {
    latestFeatures = featuresResult.value;
  }

  if (healthResult.status === "fulfilled") {
    latestHealth = healthResult.value;
  } else {
    latestHealth = { status: "offline", league_connected: false, valorant_connected: false };
  }

  if (needsMeta && metaResult?.status === "fulfilled") {
    featureMeta = metaResult.value;
    for (const cb of metaSubscribers) cb(featureMeta);
  }

  for (const cb of featureSubscribers) cb(latestFeatures);
  for (const cb of healthSubscribers) cb(latestHealth);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Starts polling. Callers should not await this — it deliberately never
 * blocks the caller on the backend actually responding; screens read
 * whatever's cached (empty at first) and redraw via onFeatureMetaUpdate /
 * onFeaturesUpdate / onHealthUpdate as real data arrives. Just polls fast
 * for a bit first, since that's cheap and gets a slow-booting backend's
 * data on screen sooner.
 */
export async function startPolling(intervalMs = 4000) {
  const maxAttempts = 20; // ~20s of fast retries while the Python backend boots
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
