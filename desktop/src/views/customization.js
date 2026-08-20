import { CUSTOMIZATION_SCREEN_CATEGORIES } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

export function renderCustomizationView(root) {
  return renderCategoryScreen(root, { categories: CUSTOMIZATION_SCREEN_CATEGORIES });
}
