import { el } from "../components.js";
import { onEvent, startEventStream } from "../event-stream.js";
import { showToast } from "../toast.js";
import { mountLeagueStatus } from "../league-status.js";
import { registerRoute, startRouter } from "../router.js";
import { startPolling } from "../state.js";
import { renderAutomationView } from "./automation.js";
import { NAV_ITEMS } from "./categories.js";
import { renderCustomizationView } from "./customization.js";
import { renderSocialView } from "./social.js";

const navRoot = document.getElementById("nav-links");
const viewRoot = document.getElementById("view-root");
const leagueStatusSlot = document.getElementById("league-status-slot");
const loadingScreen = document.getElementById("loading-screen");
const topbar = document.getElementById("topbar");

function buildNav() {
  for (const item of NAV_ITEMS) {
    const link = el("a", { href: `#${item.route}`, "data-route": item.route, class: "nav-link" }, [
      el("span", { text: item.label }),
    ]);
    navRoot.appendChild(link);
  }
}

function hideLoadingScreen() {
  if (!loadingScreen) return;
  loadingScreen.classList.add("fade-out");
  loadingScreen.addEventListener("transitionend", () => loadingScreen.remove(), { once: true });
  // Fallback removal
  setTimeout(() => { if (loadingScreen.parentNode) loadingScreen.remove(); }, 600);
}

async function bootstrap() {
  await startPolling();

  // Reveal the UI
  hideLoadingScreen();
  if (topbar) topbar.hidden = false;

  buildNav();
  mountLeagueStatus(leagueStatusSlot);
  // Until now nothing consumed the stream: every success/info the backend
  // reported was buffered and dropped.
  onEvent((entry) => showToast(entry.level, entry.message));
  startEventStream();

  registerRoute("/automation", renderAutomationView);
  registerRoute("/customization", renderCustomizationView);
  registerRoute("/social", renderSocialView);
  startRouter(viewRoot, navRoot);
}

bootstrap();
