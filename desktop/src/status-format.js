import { el } from "./components.js";
import { championSquareUrl, profileIconUrl, skinTileUrl } from "./ddragon.js";

export const STATUS_FIELD_LABELS = {
  enabled: "Enabled",
  instalock_enabled: "Instalock",
  instalock_champion: "Instalock Champion",
  autoban_enabled: "AutoBan",
  autoban_champion: "AutoBan Champion",
  disconnected: "Chat Disconnected",
  icon_id: "Current Icon",
  skin_id: "Current Skin",
};

const BOOLEAN_FIELD_PATTERN = /(^enabled$|_enabled$|^disconnected$)/;

export function isBooleanField(field, value) {
  return typeof value === "boolean" && BOOLEAN_FIELD_PATTERN.test(field);
}

export function isSpecialDisplayField(field, value) {
  if (value === null || value === undefined || value === "") return false;
  return (
    field === "instalock_champion" ||
    field === "autoban_champion" ||
    field === "icon_id" ||
    field === "skin_id"
  );
}

export function formatSpecialDisplay(field, value) {
  if (field === "instalock_champion" || field === "autoban_champion") {
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
    const img = el("img", {
      src: skinTileUrl(value),
      class: "stat-champ-thumb",
      alt: String(value),
    });
    img.onerror = () => { img.style.display = "none"; };
    return el("div", { class: "stat-champ-pill" }, [img, el("span", { text: `#${value}` })]);
  }

  return el("span", { text: String(value) });
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
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
