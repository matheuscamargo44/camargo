import { reportClientError } from "../api.js";
import { el } from "../components.js";
import { mountLeagueStatus } from "../league-status.js";
import { registerRoute, startRouter } from "../router.js";
import { startPolling } from "../state.js";
import { renderAutomationView } from "./automation.js";
import { NAV_ITEMS } from "./categories.js";
import { renderCustomizationView } from "./customization.js";
import { renderLogsView } from "./logs.js";
import { renderSocialView } from "./social.js";
import { renderValorantView } from "./valorant.js";

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

/**
 * Anything that blows up in the renderer goes to the same activity log as the
 * backend, so one copy covers both sides.
 */
function captureRendererErrors() {
  window.addEventListener("error", (event) => {
    const error = event.error;
    reportClientError(
      error?.message || event.message || "Unknown renderer error",
      error?.stack || `${event.filename}:${event.lineno}:${event.colno}`,
      "window"
    );
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportClientError(
      reason?.message || String(reason),
      reason?.stack,
      "promise"
    );
  });
}


async function bootstrap() {
  captureRendererErrors();
  await startPolling();

  // Reveal the UI
  hideLoadingScreen();
  if (topbar) topbar.hidden = false;

  buildNav();
  mountLeagueStatus(leagueStatusSlot);

  registerRoute("/automation", renderAutomationView);
  registerRoute("/customization", renderCustomizationView);
  registerRoute("/social", renderSocialView);
  registerRoute("/valorant", renderValorantView);
  registerRoute("/logs", renderLogsView);
  startRouter(viewRoot, navRoot);
}

bootstrap();
