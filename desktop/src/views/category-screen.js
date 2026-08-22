import { el } from "../components.js";
import { getFeatureMeta, onFeatureMetaUpdate, onFeaturesUpdate } from "../state.js";
import { CATEGORY_LABELS } from "./categories.js";
import { buildFeatureCard } from "./feature-card.js";

/**
 * Renders every feature belonging to `categories`, grouped into
 * subsections by their backend category, and keeps status rows live via
 * onFeaturesUpdate without rebuilding the DOM (so open forms keep their
 * typed values).
 *
 * Metadata can arrive after this first runs (a slow-starting backend — e.g.
 * antivirus scanning a freshly installed, unsigned .exe on its first launch
 * — easily takes longer than the initial retry window). Without reacting to
 * it landing late, a screen built during that window would show an empty
 * state forever, even once the backend is healthy. onFeatureMetaUpdate
 * rebuilds the screen the moment real metadata shows up.
 */
export function renderCategoryScreen(root, { categories }) {
  let disposers = [];
  let unsubscribeFeatures = null;

  function build(metaList) {
    if (unsubscribeFeatures) unsubscribeFeatures();
    for (const dispose of disposers) dispose();
    disposers = [];
    root.innerHTML = "";

    const metaByCategory = new Map();
    for (const meta of metaList) {
      if (!categories.includes(meta.category)) continue;
      if (!metaByCategory.has(meta.category)) metaByCategory.set(meta.category, []);
      metaByCategory.get(meta.category).push(meta);
    }

    if (metaByCategory.size === 0) {
      unsubscribeFeatures = null;
      root.appendChild(
        el("div", { class: "empty-state" }, [
          el("div", { class: "loading-spinner" }),
          el("span", { text: "Waiting for the backend to start…" }),
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
        const { cardEl, updateStatus, dispose } = buildFeatureCard(meta, {});
        updaters[meta.key] = updateStatus;
        disposers.push(dispose);
        list.appendChild(cardEl);
      }

      root.appendChild(list);
    }

    unsubscribeFeatures = onFeaturesUpdate((features) => {
      for (const [key, updateStatus] of Object.entries(updaters)) {
        if (features[key]) updateStatus(features[key]);
      }
    });
  }

  build(getFeatureMeta());
  const unsubscribeMeta = onFeatureMetaUpdate(build);

  return () => {
    unsubscribeMeta();
    if (unsubscribeFeatures) unsubscribeFeatures();
    for (const dispose of disposers) dispose();
  };
}
