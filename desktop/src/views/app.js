import { reportClientError } from "../api.js";
import { el } from "../components.js";
import { mountLeagueStatus } from "../league-status.js";
import { registerRoute, startRouter } from "../router.js";
import { startPolling } from "../state.js";
import { mountValorantStatus } from "../valorant-status.js";
import { NAV_ITEMS } from "./categories.js";
import { renderLeagueView } from "./league.js";
import { renderLogsView } from "./logs.js";
import { renderValorantView } from "./valorant.js";

const navRoot = document.getElementById("nav-links");
const viewRoot = document.getElementById("view-root");
const leagueStatusSlot = document.getElementById("league-status-slot");
const valorantStatusSlot = document.getElementById("valorant-status-slot");
const loadingScreen = document.getElementById("loading-screen");
const topbar = document.getElementById("topbar");

function buildNav() {
  for (const item of NAV_ITEMS) {
    const attrs = { href: `#${item.route}`, "data-route": item.route, class: "nav-link" };
    if (item.matchPrefix) attrs["data-match-prefix"] = item.matchPrefix;
    const link = el("a", attrs, [el("span", { text: item.label })]);
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
  mountValorantStatus(valorantStatusSlot);
  mountLeagueStatus(leagueStatusSlot);

  registerRoute("/league/automation", (root) => renderLeagueView(root, "Automation"));
  registerRoute("/league/customization", (root) => renderLeagueView(root, "Customization"));
  registerRoute("/league/social", (root) => renderLeagueView(root, "Social"));
  registerRoute("/valorant", renderValorantView);
  registerRoute("/logs", renderLogsView);
  startRouter(viewRoot, navRoot);
}

bootstrap();
