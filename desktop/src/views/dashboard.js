import { el } from "../components.js";
import { getFeatureMeta, onFeaturesUpdate } from "../state.js";

const CATEGORY_ROUTE = {
  Automation: "#/automation",
  "Game Tools": "#/automation",
  Customization: "#/customization",
  Social: "#/social",
  Settings: "#/social",
};

function summarize(status) {
  const { key, ...rest } = status || {};
  return Object.entries(rest)
    .slice(0, 2)
    .map(([field, value]) => `${field}: ${value}`)
    .join(" · ");
}

function buildOverviewCard(meta) {
  return el("a", { class: "overview-card", href: CATEGORY_ROUTE[meta.category] || "#/dashboard" }, [
    el("h3", { text: meta.title }),
    el("p", { class: "overview-card-status" }),
  ]);
}

export function renderDashboardView(root) {
  root.appendChild(el("h1", { class: "view-title", text: "Painel" }));

  const grid = el("div", { class: "overview-grid" });
  root.appendChild(grid);

  const cardsByKey = {};
  for (const item of getFeatureMeta()) {
    const cardEl = buildOverviewCard(item);
    cardsByKey[item.key] = cardEl;
    grid.appendChild(cardEl);
  }

  return onFeaturesUpdate((features) => {
    for (const [key, status] of Object.entries(features)) {
      const cardEl = cardsByKey[key];
      if (!cardEl) continue;
      cardEl.querySelector(".overview-card-status").textContent = summarize(status);
    }
  });
}
