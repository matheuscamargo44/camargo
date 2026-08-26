import { el } from "../components.js";
import { getFeatureMeta, onFeatureMetaUpdate, onFeaturesUpdate } from "../state.js";
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
 *
 * `excludeKeys` hides specific features from the list without unregistering
 * them backend-side — e.g. valorant_rank still needs to run and update
 * `features.valorant_rank` for the topbar status pill, it just shouldn't
 * also show its own card here.
 */
export function renderCategoryScreen(root, { categories, excludeKeys = [] }) {
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
      if (excludeKeys.includes(meta.key)) continue;
      if (!metaByCategory.has(meta.category)) metaByCategory.set(meta.category, []);
      metaByCategory.get(meta.category).push(meta);
    }

    if (metaByCategory.size === 0) {
      unsubscribeFeatures = null;
      root.appendChild(el("div", { class: "empty-state" }, [el("div", { class: "loading-spinner" })]));
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

  // onFeatureMetaUpdate immediately invokes its callback with whatever
  // metadata is already cached (see state.js) - calling build() here too
  // in that case built every card (and kicked off each one's DDragon/
  // valorant-api asset backfill) twice in a row for identical data. Only
  // needed as a direct call for the genuinely-empty case, to show the
  // loading placeholder before metadata has ever arrived at all.
  if (getFeatureMeta().length === 0) {
    build([]);
  }
  const unsubscribeMeta = onFeatureMetaUpdate(build);

  return () => {
    unsubscribeMeta();
    if (unsubscribeFeatures) unsubscribeFeatures();
    for (const dispose of disposers) dispose();
  };
}
