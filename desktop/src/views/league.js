import { el } from "../components.js";
import { LEAGUE_SUB_TABS } from "./categories.js";
import { renderCategoryScreen } from "./category-screen.js";

/**
 * The League of Legends tab: a sub-nav row (Automation/Customization/Social)
 * plus that category's feature list below it. Registered once per sub-route
 * in app.js, each call just fixing which category is active.
 */
export function renderLeagueView(root, activeCategory) {
  const subnav = el("div", { class: "subnav" });
  for (const tab of LEAGUE_SUB_TABS) {
    subnav.appendChild(
      el(
        "a",
        {
          href: `#${tab.route}`,
          class: `subnav-link${tab.category === activeCategory ? " active" : ""}`,
        },
        [tab.label]
      )
    );
  }
  root.appendChild(subnav);

  const content = el("div", { class: "subnav-content" });
  root.appendChild(content);

  return renderCategoryScreen(content, { categories: [activeCategory] });
}
