import { el } from "./components.js";
import { onHealthUpdate } from "./state.js";

/**
 * Mounts a compact, persistent League-client status indicator into
 * `container` (lives in the top bar, next to the nav, visible on every
 * screen). Returns the onHealthUpdate unsubscribe function.
 */
export function mountLeagueStatus(container) {
  const indicator = el("div", { class: "league-status-compact" }, [
    el("span", { class: "league-status-dot" }),
    el("span", { class: "league-status-text", text: "Verificando..." }),
  ]);
  container.appendChild(indicator);

  return onHealthUpdate((health) => {
    const connected = Boolean(health.league_connected);
    indicator.className = `league-status-compact ${connected ? "connected" : "offline"}`;
    indicator.querySelector(".league-status-text").textContent = connected
      ? "League conectado"
      : "League não encontrado";
  });
}
