/**
 * Public VALORANT data (valorant-api.com). No auth needed — same community
 * API the agent picker uses for portraits.
 */

const COMPETITIVE_TIERS_URL = "https://valorant-api.com/v1/competitivetiers";
const AGENTS_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true";

let cachedAgentIconsMap = null;
let agentIconsPromise = null;

/** Agent display name (lowercased) -> portrait icon URL. The backend stores
 * agents by name (e.g. "Reyna"), not uuid, so this maps the same way.
 */
export async function getAgentIconsMap() {
  if (cachedAgentIconsMap) return cachedAgentIconsMap;
  if (agentIconsPromise) return agentIconsPromise;

  agentIconsPromise = fetch(AGENTS_URL)
    .then((r) => r.json())
    .then((data) => {
      cachedAgentIconsMap = {};
      for (const agent of data.data || []) {
        if (!agent.displayName) continue;
        cachedAgentIconsMap[agent.displayName.toLowerCase()] = agent.displayIconSmall || agent.displayIcon || "";
      }
      return cachedAgentIconsMap;
    })
    .catch((error) => {
      agentIconsPromise = null;
      throw error;
    });
  return agentIconsPromise;
}

/** Synchronous lookup from whatever's already cached; "" if not loaded yet. */
export function getAgentIcon(agentName) {
  if (cachedAgentIconsMap) return cachedAgentIconsMap[String(agentName).toLowerCase()] || "";
  return "";
}

let cachedTiersMap = null;
let tiersPromise = null;

export async function getRankTiersMap() {
  if (cachedTiersMap) return cachedTiersMap;
  if (tiersPromise) return tiersPromise;

  tiersPromise = fetch(COMPETITIVE_TIERS_URL)
    .then((r) => r.json())
    .then((data) => {
      const tierSets = data.data || [];
      // The tier→name/icon mapping changes over time (e.g. Ascendant was
      // added later); the last entry is always the current episode's set.
      const currentSet = tierSets[tierSets.length - 1];
      cachedTiersMap = {};
      for (const tier of currentSet?.tiers || []) {
        cachedTiersMap[tier.tier] = {
          name: tier.tierName || "Unranked",
          icon: tier.largeIcon || tier.smallIcon || "",
        };
      }
      return cachedTiersMap;
    })
    .catch((error) => {
      tiersPromise = null;
      throw error;
    });
  return tiersPromise;
}

/** Synchronous lookup from whatever's already cached; null if not loaded yet. */
export function getRankTierInfo(tier) {
  if (cachedTiersMap && cachedTiersMap[tier]) return cachedTiersMap[tier];
  return null;
}
