import { fetchSummoner } from "./api.js";
import { el } from "./components.js";
import { profileIconUrl, rankedEmblemUrl } from "./ddragon.js";
import { onHealthUpdate } from "./state.js";

/**
 * Mounts a compact, persistent League-client status & summoner badge indicator
 * into `container`. Returns the onHealthUpdate unsubscribe function.
 */
export function mountLeagueStatus(container) {
  const indicator = el("div", { class: "league-status-compact", "aria-live": "polite" }, [
    el("span", { class: "league-status-dot" }),
    el("span", { class: "league-status-text", text: "Checking..." }),
  ]);
  container.appendChild(indicator);

  let lastSummonerFetch = 0;
  let cachedSummoner = null;

  async function updateIndicator(connected) {
    if (!connected) {
      cachedSummoner = null;
      indicator.className = "league-status-compact offline";
      indicator.innerHTML = "";
      indicator.appendChild(el("span", { class: "league-status-dot" }));
      indicator.appendChild(el("span", { class: "league-status-text", text: "League Not Detected" }));
      return;
    }

    const now = Date.now();
    if (!cachedSummoner || now - lastSummonerFetch > 10000) {
      lastSummonerFetch = now;
      cachedSummoner = await fetchSummoner();
    }

    indicator.className = "league-status-compact connected";
    indicator.innerHTML = "";

    if (cachedSummoner && cachedSummoner.connected) {
      const iconSrc = profileIconUrl(cachedSummoner.profile_icon_id);
      const tier = cachedSummoner.ranked_tier || "UNRANKED";
      const division = cachedSummoner.ranked_division ? ` ${cachedSummoner.ranked_division}` : "";
      const rankText = tier === "UNRANKED" ? "Unranked" : `${tier.charAt(0) + tier.slice(1).toLowerCase()}${division}`;
      const emblem = rankedEmblemUrl(tier);

      const avatarWrap = el("div", { class: "summoner-avatar-wrap" }, [
        el("img", { src: iconSrc, class: "summoner-avatar-img", alt: "Profile Icon" }),
        el("span", { class: "summoner-level-badge", text: String(cachedSummoner.summoner_level) }),
      ]);

      const nameRow = el("div", { class: "summoner-info-text" }, [
        el("span", { class: "summoner-name", text: cachedSummoner.display_name }),
        cachedSummoner.tag_line ? el("span", { class: "summoner-tag", text: `#${cachedSummoner.tag_line}` }) : null,
      ]);

      const rankBadge = el("div", { class: `summoner-rank-pill rank-${tier.toLowerCase()}` }, [
        emblem ? el("img", { src: emblem, class: "summoner-rank-icon", alt: tier }) : null,
        el("span", { text: rankText }),
      ]);

      indicator.appendChild(avatarWrap);
      indicator.appendChild(nameRow);
      indicator.appendChild(rankBadge);
      indicator.appendChild(el("span", { class: "league-status-dot" }));
    } else {
      indicator.appendChild(el("span", { class: "league-status-dot" }));
      indicator.appendChild(el("span", { class: "league-status-text", text: "League Connected" }));
    }
  }

  return onHealthUpdate((health) => {
    updateIndicator(Boolean(health.league_connected));
  });
}
