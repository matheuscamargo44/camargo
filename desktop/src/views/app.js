import { el } from "../components.js";
import { registerRoute, startRouter } from "../router.js";
import { startPolling } from "../state.js";
import { renderAutomationView } from "./automation.js";
import { NAV_ITEMS } from "./categories.js";
import { renderCustomizationView } from "./customization.js";
import { renderDashboardView } from "./dashboard.js";
import { renderSocialView } from "./social.js";

const navRoot = document.getElementById("nav-links");
const viewRoot = document.getElementById("view-root");

function buildNav() {
  for (const item of NAV_ITEMS) {
    const link = el("a", { href: `#${item.route}`, "data-route": item.route, class: "nav-link" }, [
      el("span", { text: item.label }),
    ]);
    navRoot.appendChild(link);
  }
}

async function bootstrap() {
  await startPolling();

  buildNav();
  registerRoute("/dashboard", renderDashboardView);
  registerRoute("/automation", renderAutomationView);
  registerRoute("/customization", renderCustomizationView);
  registerRoute("/social", renderSocialView);
  startRouter(viewRoot, navRoot);
}

bootstrap();
