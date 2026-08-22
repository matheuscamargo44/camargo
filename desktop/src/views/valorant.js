import { VALORANT_SCREEN_CATEGORIES } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

export function renderValorantView(root) {
  // valorant_rank keeps running so the topbar status pill (valorant-status.js)
  // has data, but its own card is redundant with that pill and hidden here.
  return renderCategoryScreen(root, { categories: VALORANT_SCREEN_CATEGORIES, excludeKeys: ["valorant_rank"] });
}
