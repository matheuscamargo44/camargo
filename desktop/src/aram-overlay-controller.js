import { fetchFeatureStatus } from "./api.js";
import { isLeagueConnected, onFeaturesUpdate } from "./state.js";

const FEATURE_KEY = "aram_augment_advisor";

// Only worth polling this fast while the feature is on and there's a
// League client to poll at all - the badge needs to appear within a
// several-second pick window, far tighter than the general 4s poll can
// afford (see backend/docs for why this isn't the bulk /features endpoint).
const FAST_POLL_INTERVAL_MS = 600;

let fastPollTimer = null;
let lastRegionKey = null;

function buildBadges(recommendation) {
  const regions = recommendation.regions || [];
  const augmentsBySlot = new Map((recommendation.augments || []).map((a) => [a.slot, a]));

  return regions
    .map((region) => {
      const augment = augmentsBySlot.get(region.slot);
      if (!augment) return null;
      return {
        slot: region.slot,
        x: region.x,
        y: region.y,
        w: region.w,
        h: region.h,
        name: augment.name,
        iconUrl: augment.icon_url,
        tier: augment.tier,
        ambiguous: Boolean(augment.ambiguous),
        isBest: region.slot === recommendation.best_slot,
      };
    })
    .filter(Boolean);
}

async function pollOnce() {
  let status;
  try {
    status = await fetchFeatureStatus(FEATURE_KEY);
  } catch {
    return; // a stalled backend request just skips this tick, not a fatal error
  }

  const recommendation = status.recommendation;
  if (!recommendation || !recommendation.active) {
    if (lastRegionKey !== null) {
      lastRegionKey = null;
      window.camargo.hideAramOverlay();
    }
    return;
  }

  // Avoid re-sending the same badges every 600ms while nothing changed.
  const key = `${recommendation.trigger}:${recommendation.champion}`;
  if (key === lastRegionKey) return;
  lastRegionKey = key;

  window.camargo.showAramOverlay(buildBadges(recommendation));
}

function startFastPolling() {
  if (fastPollTimer !== null) return;
  fastPollTimer = setInterval(pollOnce, FAST_POLL_INTERVAL_MS);
  pollOnce();
}

function stopFastPolling() {
  if (fastPollTimer === null) return;
  clearInterval(fastPollTimer);
  fastPollTimer = null;
  lastRegionKey = null;
  window.camargo.hideAramOverlay();
}

export function initAramOverlayController() {
  onFeaturesUpdate((features) => {
    const enabled = Boolean(features[FEATURE_KEY]?.enabled);
    if (enabled && isLeagueConnected()) {
      startFastPolling();
    } else {
      stopFastPolling();
    }
  });
}
