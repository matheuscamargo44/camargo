import { el } from "./components.js";
import { championSquareUrl, profileIconUrl, skinTileUrl, getSkinInfo, getSkinsMap } from "./ddragon.js";

export const STATUS_FIELD_LABELS = {
  enabled: "Enabled",
  instalock_enabled: "Instalock",
  instalock_champion: "Instalock Champion",
  autoban_enabled: "AutoBan",
  autoban_champion: "AutoBan Champion",
  target_champion: "Target Champion",
  instalock_agent: "Agent",
  region: "Region",
  summoners: "Invite Group",
  current_title: "Current Title",
  tier: "Ranked Chat Tier",
  pending_count: "Pending Requests",
  disconnected: "Chat Disconnected",
  icon_id: "Current Icon",
  skin_id: "Current Skin",
  key_fragments: "Key Fragments",
  chests: "Available Containers",
  champion_shards: "Champion Shards",
  skin_shards: "Skin Shards",
  total_shards: "Total Loot Shards",
  availability: "Availability",
};

export function isSpecialDisplayField(field, value) {
  if (arguments.length > 1 && (value === null || value === undefined || value === "")) return false;
  return (
    field === "instalock_champion" ||
    field === "autoban_champion" ||
    field === "target_champion" ||
    field === "icon_id" ||
    field === "skin_id"
  );
}

export function formatSpecialDisplay(field, value) {
  if (field === "instalock_champion" || field === "autoban_champion" || field === "target_champion") {
    const strVal = String(value);
    if (!strVal || strVal.toLowerCase() === "none") {
      return el("span", { text: "None" });
    }

    const img = el("img", {
      src: championSquareUrl(strVal),
      class: "stat-champ-thumb",
      alt: strVal,
    });
    img.onerror = () => { img.style.display = "none"; };

    return el("div", { class: "stat-champ-pill" }, [img, el("span", { text: strVal })]);
  }

  if (field === "icon_id") {
    const img = el("img", {
      src: profileIconUrl(value),
      class: "stat-champ-thumb round",
      alt: String(value),
    });
    img.onerror = () => { img.style.display = "none"; };
    return el("div", { class: "stat-champ-pill" }, [img, el("span", { text: `#${value}` })]);
  }

  if (field === "skin_id") {
    const skinInfo = getSkinInfo(value);
    const labelText = skinInfo ? skinInfo.name : `#${value}`;
    const img = el("img", {
      src: skinInfo?.imgUrl || skinTileUrl(value),
      class: "stat-champ-thumb",
      alt: labelText,
    });
    if (!skinInfo?.imgUrl && !skinTileUrl(value)) {
      img.style.display = "none";
    }
    img.onerror = () => { img.style.display = "none"; };
    const labelSpan = el("span", { text: labelText });
    const pill = el("div", { class: "stat-champ-pill" }, [img, labelSpan]);

    if (!skinInfo) {
      getSkinsMap().then((map) => {
        const updated = map[String(value)];
        if (updated) {
          if (updated.imgUrl) {
            img.src = updated.imgUrl;
            img.style.display = "";
          }
          if (updated.name) {
            labelSpan.textContent = updated.name;
          }
        }
      });
    }

    return pill;
  }

  return el("span", { text: String(value) });
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  const str = String(value).toLowerCase();
  if (str === "chat") return "Online";
  if (str === "mobile") return "Mobile";
  if (str === "away") return "Away";
  if (str === "dnd") return "Do Not Disturb";
  if (str === "offline") return "Offline";
  return String(value);
}

/** Small colored pill for a boolean flag — green when the feature is actively on. */
export function statusPill(field, value) {
  if (field === "disconnected") {
    // "disconnected: true" means chat is OFF — invert so green means connected/live.
    return el("span", { class: `status-pill ${value ? "" : "on"}`, text: value ? "Disconnected" : "Connected" });
  }
  return el("span", { class: `status-pill ${value ? "on" : ""}`, text: value ? "Active" : "Inactive" });
}
