/**
 * Data Dragon & CommunityDragon asset helper.
 * Manages version cache and generates asset URLs.
 */

const VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json";
let cachedVersion = "14.24.1"; // sensible fallback
let versionPromise = null;
let cachedChampionsMap = null; // { [lowerName]: { id, name, imgUrl } }

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

export function skinTileUrl(skinId) {
  if (!skinId && skinId !== 0) return "";
  const champId = Math.floor(Number(skinId) / 1000);
  return `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-tiles/${champId}/${skinId}.jpg`;
}

export function rankedEmblemUrl(tier) {
  if (!tier || tier === "UNRANKED") return "";
  return `https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-shared-components/global/default/images/${tier.toLowerCase()}.png`;
}

export async function getChampionsMap() {
  if (cachedChampionsMap) return cachedChampionsMap;
  const version = await getLatestVersion();
  try {
    const res = await fetch(`https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/champion.json`);
    const data = await res.json();
    cachedChampionsMap = {};
    for (const champ of Object.values(data.data)) {
      const entry = {
        id: champ.id,
        name: champ.name,
        key: champ.key,
        imgUrl: `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${champ.image.full}`,
      };
      cachedChampionsMap[champ.name.toLowerCase()] = entry;
      cachedChampionsMap[champ.id.toLowerCase()] = entry;
    }
    return cachedChampionsMap;
  } catch {
    return {};
  }
}
