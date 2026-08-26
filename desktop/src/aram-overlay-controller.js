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
// Bumped by stopFastPolling - lets an in-flight pollOnce that resolves
// *after* polling stopped recognize it's stale and do nothing.
let pollGeneration = 0;
// Overlapping 600ms polls are routine against a backend doing screen
// capture + an OP.GG lookup - lets a response recognize a *newer* request
// has already been sent (or already resolved) since it went out, so an
// out-of-order-arriving older response can't paint stale badges over a
// newer game's.
let latestSequence = 0;

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
        rank: augment.rank ?? null,
        justification: augment.justification ?? null,
        ambiguous: Boolean(augment.ambiguous),
        isBest: region.slot === recommendation.best_slot,
      };
    })
    .filter(Boolean);
}

async function pollOnce() {
  const generation = pollGeneration;
  const sequence = ++latestSequence;

  let status;
  try {
    status = await fetchFeatureStatus(FEATURE_KEY);
  } catch {
    return; // a stalled backend request just skips this tick, not a fatal error
  }

  // This request may have been sent, then outlived by polling stopping
  // entirely (stale, would re-show an overlay nothing is left to hide
  // again) or by a newer request that has already been sent or already
  // resolved (out of order, would paint an older game's badges over a
  // newer one). Either way, this result no longer reflects "now".
  if (generation !== pollGeneration || sequence !== latestSequence) return;

  const recommendation = status.recommendation;
  if (!recommendation || !recommendation.active) {
    if (lastRegionKey !== null) {
      lastRegionKey = null;
      window.camargo.hideAramOverlay();
    }
    return;
  }

  // Avoid re-sending the same badges every 600ms while nothing changed.
  // Keyed on the actual identified augments (not just champion) - the
  // recommendation has no "trigger" field to key on once the picker's
  // presence is detected directly rather than inferred from level-ups,
  // and the same champion can still get a genuinely different offer.
  const key = (recommendation.augments || []).map((a) => `${a.slot}:${a.augment_id}`).join(",");
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
  pollGeneration += 1;
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
