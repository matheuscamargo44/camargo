import { AUTOMATION_SCREEN_CATEGORIES } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

export function renderAutomationView(root) {
  return renderCategoryScreen(root, { categories: AUTOMATION_SCREEN_CATEGORIES });
}
