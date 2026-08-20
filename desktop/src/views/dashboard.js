import { el } from "../components.js";
import { getFeatureMeta, onFeaturesUpdate, onHealthUpdate } from "../state.js";
import { formatValue, isBooleanField, statusPill } from "../status-format.js";

const CATEGORY_ROUTE = {
  Automation: "#/automation",
  "Game Tools": "#/automation",
  Customization: "#/customization",
  Social: "#/social",
  Settings: "#/social",
};

function renderStatusSummary(container, status) {
  container.innerHTML = "";
  const { key, ...rest } = status || {};
  const entries = Object.entries(rest).slice(0, 2);
  for (const [field, value] of entries) {
    if (isBooleanField(field, value)) {
      container.appendChild(statusPill(field, value));
    } else {
      container.appendChild(el("span", { class: "overview-card-status-text", text: formatValue(value) }));
    }
  }
}

function buildOverviewCard(meta) {
  const status = el("div", { class: "overview-card-status" });
  return {
    cardEl: el("a", { class: "overview-card", href: CATEGORY_ROUTE[meta.category] || "#/dashboard" }, [
      el("h3", { text: meta.title }),
      status,
    ]),
    statusEl: status,
  };
}

export function renderDashboardView(root) {
  const leagueStatus = el("div", { class: "league-status" }, [
    el("span", { class: "league-status-dot" }),
    el("span", { class: "league-status-text", text: "Verificando cliente do League..." }),
  ]);
  root.appendChild(leagueStatus);

  const grid = el("div", { class: "overview-grid" });
  root.appendChild(grid);

  const cardsByKey = {};
  for (const item of getFeatureMeta()) {
    const { cardEl, statusEl } = buildOverviewCard(item);
    cardsByKey[item.key] = statusEl;
    grid.appendChild(cardEl);
  }

  const unsubscribeFeatures = onFeaturesUpdate((features) => {
    for (const [key, status] of Object.entries(features)) {
      const statusEl = cardsByKey[key];
      if (statusEl) renderStatusSummary(statusEl, status);
    }
  });

  const unsubscribeHealth = onHealthUpdate((health) => {
    const connected = Boolean(health.league_connected);
    leagueStatus.className = `league-status ${connected ? "connected" : "offline"}`;
    leagueStatus.querySelector(".league-status-text").textContent = connected
      ? "Cliente do League conectado"
      : "Cliente do League não encontrado — abra o LoL para usar as automações";
  });

  return () => {
    unsubscribeFeatures();
    unsubscribeHealth();
  };
}
