import { el } from "./components.js";
import { onHealthUpdate } from "./state.js";

/**
 * Mounts a compact, persistent VALORANT-client status indicator into
 * `container`. Mirrors league-status.js's dot+text shape; there's no
 * per-player profile endpoint on the Valorant side (yet), so this stays a
 * plain connection indicator rather than an avatar/rank card.
 */
export function mountValorantStatus(container) {
  const indicator = el("div", { class: "league-status-compact", "aria-live": "polite" }, [
    el("span", { class: "league-status-dot" }),
    el("span", { class: "league-status-text", text: "Checking..." }),
  ]);
  container.appendChild(indicator);

  function updateIndicator(connected) {
    indicator.className = `league-status-compact ${connected ? "connected" : "offline"}`;
    indicator.innerHTML = "";
    indicator.appendChild(el("span", { class: "league-status-dot" }));
    indicator.appendChild(
      el("span", { class: "league-status-text", text: connected ? "VALORANT Connected" : "VALORANT Not Detected" })
    );
  }

  return onHealthUpdate((health) => {
    updateIndicator(Boolean(health.valorant_connected));
  });
}
