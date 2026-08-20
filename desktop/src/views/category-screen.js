import { el } from "../components.js";
import { getFeatureMeta, onFeaturesUpdate } from "../state.js";
import { CATEGORY_LABELS } from "./categories.js";
import { buildFeatureCard } from "./feature-card.js";

/**
 * Renders every feature belonging to `categories`, grouped into
 * subsections by their backend category, and keeps status rows live via
 * onFeaturesUpdate without rebuilding the DOM (so open forms keep their
 * typed values).
 */
export function renderCategoryScreen(root, { title, categories }) {
  root.appendChild(el("h1", { class: "view-title", text: title }));

  const metaByCategory = new Map();
  for (const meta of getFeatureMeta()) {
    if (!categories.includes(meta.category)) continue;
    if (!metaByCategory.has(meta.category)) metaByCategory.set(meta.category, []);
    metaByCategory.get(meta.category).push(meta);
  }

  if (metaByCategory.size === 0) {
    root.appendChild(el("p", { class: "empty-state", text: "Backend indisponível ou nenhuma feature encontrada." }));
    return;
  }

  const updaters = {};

  for (const category of categories) {
    const metas = metaByCategory.get(category);
    if (!metas || metas.length === 0) continue;

    root.appendChild(el("h2", { class: "section-title", text: CATEGORY_LABELS[category] || category }));
    const grid = el("div", { class: "card-grid" });

    for (const meta of metas) {
      const { cardEl, updateStatus } = buildFeatureCard(meta, {});
      updaters[meta.key] = updateStatus;
      grid.appendChild(cardEl);
    }

    root.appendChild(grid);
  }

  return onFeaturesUpdate((features) => {
    for (const [key, updateStatus] of Object.entries(updaters)) {
      if (features[key]) updateStatus(features[key]);
    }
  });
}
