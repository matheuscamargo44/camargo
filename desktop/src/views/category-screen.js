import { el } from "../components.js";
import { icon } from "../icons.js";
import { getFeatureMeta, onFeaturesUpdate } from "../state.js";
import { CATEGORY_LABELS } from "./categories.js";
import { buildFeatureCard } from "./feature-card.js";

/**
 * Renders every feature belonging to `categories`, grouped into
 * subsections by their backend category, and keeps status rows live via
 * onFeaturesUpdate without rebuilding the DOM (so open forms keep their
 * typed values).
 */
export function renderCategoryScreen(root, { categories }) {
  const metaByCategory = new Map();
  for (const meta of getFeatureMeta()) {
    if (!categories.includes(meta.category)) continue;
    if (!metaByCategory.has(meta.category)) metaByCategory.set(meta.category, []);
    metaByCategory.get(meta.category).push(meta);
  }

  if (metaByCategory.size === 0) {
    root.appendChild(
      el("div", { class: "empty-state" }, [
        icon("monitor"),
        el("span", { text: "Backend offline or no features found." }),
      ])
    );
    return;
  }

  const updaters = {};

  for (const category of categories) {
    const metas = metaByCategory.get(category);
    if (!metas || metas.length === 0) continue;

    const list = el("div", { class: "feature-list" });

    for (const meta of metas) {
      const { cardEl, updateStatus } = buildFeatureCard(meta, {});
      updaters[meta.key] = updateStatus;
      list.appendChild(cardEl);
    }

    root.appendChild(list);
  }

  return onFeaturesUpdate((features) => {
    for (const [key, updateStatus] of Object.entries(updaters)) {
      if (features[key]) updateStatus(features[key]);
    }
  });
}
