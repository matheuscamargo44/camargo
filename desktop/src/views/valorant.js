import { VALORANT_SCREEN_CATEGORIES } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

export function renderValorantView(root) {
  return renderCategoryScreen(root, { categories: VALORANT_SCREEN_CATEGORIES });
}
