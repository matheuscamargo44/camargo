import { el } from "./components.js";
import { onFeaturesUpdate, onHealthUpdate } from "./state.js";
import { getRankTierInfo, getRankTiersMap } from "./valorant-data.js";

/** Tier icon + name + RR, reusing the same lazy-resolve-then-backfill trick
 * as the Rank feature card. No rank-specific color class here — Valorant's
 * tier set (Ascendant, Immortal, Radiant) doesn't map onto League's
 * rank-* CSS classes, so this stays neutral instead of mis-coloring them.
 */
function buildRankPill(tier, rr) {
  const info = getRankTierInfo(tier);
  const labelText = info ? `${info.name}${rr != null ? ` · ${rr} RR` : ""}` : `Tier ${tier}`;
  const pill = el("div", { class: "summoner-rank-pill" });

  function fill(node) {
    pill.innerHTML = "";
    if (node.icon) {
      const img = el("img", { src: node.icon, class: "summoner-rank-icon", alt: node.name });
      img.onerror = () => { img.style.display = "none"; };
      pill.appendChild(img);
    }
    pill.appendChild(el("span", { text: node.label }));
  }

  fill({ icon: info?.icon, label: labelText });

  if (!info) {
    getRankTiersMap().then((map) => {
      const updated = map[tier];
      if (updated) {
        fill({ icon: updated.icon, label: `${updated.name}${rr != null ? ` · ${rr} RR` : ""}` });
      }
    });
  }

  return pill;
}

/**
 * Mounts a compact, persistent VALORANT-client status indicator into
 * `container`. Mirrors league-status.js's shape (dot, name#tag, rank pill),
 * sourced from the valorant_rank feature's status instead of a dedicated
 * summoner-style endpoint.
 */
export function mountValorantStatus(container) {
  const indicator = el("div", { class: "league-status-compact", "aria-live": "polite" }, [
    el("span", { class: "league-status-dot" }),
    el("span", { class: "league-status-text", text: "Checking..." }),
  ]);
  container.appendChild(indicator);

  let connected = false;
  let rank = null;

  function render() {
    indicator.innerHTML = "";

    if (!connected) {
      indicator.className = "league-status-compact offline";
      indicator.appendChild(el("span", { class: "league-status-dot" }));
      indicator.appendChild(el("span", { class: "league-status-text", text: "VALORANT Not Detected" }));
      return;
    }

    indicator.className = "league-status-compact connected";

    if (rank && rank.player_name) {
      const nameRow = el("div", { class: "summoner-info-text" }, [
        el("span", { class: "summoner-name", text: rank.player_name }),
        rank.player_tag ? el("span", { class: "summoner-tag", text: `#${rank.player_tag}` }) : null,
      ]);
      indicator.appendChild(nameRow);
      if (rank.tier != null) {
        indicator.appendChild(buildRankPill(rank.tier, rank.rr));
      }
      indicator.appendChild(el("span", { class: "league-status-dot" }));
    } else {
      indicator.appendChild(el("span", { class: "league-status-dot" }));
      indicator.appendChild(el("span", { class: "league-status-text", text: "VALORANT Connected" }));
    }
  }

  const unsubscribeHealth = onHealthUpdate((health) => {
    connected = Boolean(health.valorant_connected);
    render();
  });
  const unsubscribeFeatures = onFeaturesUpdate((features) => {
    rank = features.valorant_rank || null;
    render();
  });

  return () => {
    unsubscribeHealth();
    unsubscribeFeatures();
  };
}
