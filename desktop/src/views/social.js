import { SOCIAL_SCREEN_CATEGORIES } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

export function renderSocialView(root) {
  return renderCategoryScreen(root, { categories: SOCIAL_SCREEN_CATEGORIES });
}
