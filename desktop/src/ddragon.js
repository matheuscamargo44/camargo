/**
 * Data Dragon & CommunityDragon asset helper.
 * Manages version cache and generates asset URLs.
 */

const VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json";
let cachedVersion = "14.24.1"; // sensible fallback
let versionPromise = null;

export async function getLatestVersion() {
  if (versionPromise) return versionPromise;
  versionPromise = fetch(VERSIONS_URL)
    .then((r) => r.json())
    .then((versions) => {
      if (Array.isArray(versions) && versions.length > 0) {
        cachedVersion = versions[0];
      }
      return cachedVersion;
    })
    .catch(() => cachedVersion);
  return versionPromise;
}

// Start prefetching version immediately
getLatestVersion();

export function profileIconUrl(iconId, version = cachedVersion) {
  if (!iconId && iconId !== 0) return "";
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/profileicon/${iconId}.png`;
}

export function championSquareUrl(champNameOrId, version = cachedVersion) {
  if (!champNameOrId) return "";
  const clean = champNameOrId.replace(/[^a-zA-Z0-9]/g, "");
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${clean}.png`;
}

const SKINS_URL =
  "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/skins.json";
let cachedSkinsMap = null;
let skinsPromise = null;

/** Champion folder name out of ".../ASSETS/Characters/<Champion>/..." */
function championFromPath(loadScreenPath) {
  const marker = "ASSETS/Characters/";
  const markerStart = (loadScreenPath || "").indexOf(marker);
  if (markerStart === -1) return "";
  const nameStart = markerStart + marker.length;
  const nameEnd = loadScreenPath.indexOf("/", nameStart);
  // Without the trailing slash there is no name to read: substring() would
  // happily swap its arguments and return the head of the path instead.
  if (nameEnd === -1) return "";
  return loadScreenPath.substring(nameStart, nameEnd);
}

export async function getSkinsMap() {
  if (cachedSkinsMap) return cachedSkinsMap;
  if (skinsPromise) return skinsPromise;

  skinsPromise = fetch(SKINS_URL)
    .then((r) => r.json())
    .then((data) => {
      cachedSkinsMap = {};
      for (const [skinId, skinData] of Object.entries(data)) {
        const rawPath =
          skinData.tilePath ||
          skinData.splashPath ||
          skinData.loadScreenPath ||
          skinData.uncenteredSplashPath;
        let imgUrl = "";
        if (rawPath) {
          const cleanPath = rawPath.replace(/^\/lol-game-data\/assets\//i, "").toLowerCase();
          imgUrl = `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/${cleanPath}`;
        }
        cachedSkinsMap[String(skinId)] = {
          id: Number(skinId),
          name: skinData.isBase ? "Default" : skinData.name || "Default",
          champion: championFromPath(skinData.loadScreenPath),
          imgUrl,
        };
      }
      return cachedSkinsMap;
    })
    .catch((error) => {
      // Drop the memoized rejection: keeping it would leave every later call
      // returning an empty map until the app restarts.
      skinsPromise = null;
      throw error;
    });
  return skinsPromise;
}

let cachedSkinList = null;

/**
 * Same data as getSkinsMap(), as a list sorted by champion then skin id, ready
 * for the picker. Shares the single skins.json download.
 */
export async function getSkinList() {
  if (cachedSkinList) return cachedSkinList;

  const map = await getSkinsMap();
  const skins = Object.values(map)
    .filter((skin) => skin.id >= 1000)
    .sort((a, b) => a.champion.localeCompare(b.champion) || a.id - b.id);

  cachedSkinList = skins;
  return cachedSkinList;
}

// Prefetch skins map immediately; failures are retried on first real use
getSkinsMap().catch(() => {});

export function getSkinInfo(skinId) {
  if (cachedSkinsMap && cachedSkinsMap[String(skinId)]) {
    return cachedSkinsMap[String(skinId)];
  }
  return null;
}

export function skinTileUrl(skinId) {
  const info = getSkinInfo(skinId);
  return info?.imgUrl || "";
}

export function rankedEmblemUrl(tier) {
  if (!tier || tier === "UNRANKED") return "";
  return `https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/${tier.toLowerCase()}.png`;
}
