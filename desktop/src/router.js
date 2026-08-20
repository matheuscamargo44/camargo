import { el } from "./components.js";
import { icon } from "./icons.js";

const routes = new Map();
let activeCleanup = null;
let viewRoot = null;
let navLinksRoot = null;

export function registerRoute(path, renderFn) {
  routes.set(path, renderFn);
}

function defaultPath() {
  return routes.keys().next().value;
}

function currentPath() {
  const hash = window.location.hash.replace(/^#/, "");
  return routes.has(hash) ? hash : defaultPath();
}

function updateActiveNav(path) {
  if (!navLinksRoot) return;
  for (const link of navLinksRoot.querySelectorAll("[data-route]")) {
    link.classList.toggle("active", link.dataset.route === path);
    link.setAttribute("aria-current", link.dataset.route === path ? "page" : "false");
  }
}

function render() {
  const path = currentPath();
  updateActiveNav(path);

  if (typeof activeCleanup === "function") {
    activeCleanup();
    activeCleanup = null;
  }

  viewRoot.innerHTML = "";
  // Add enter animation class
  viewRoot.classList.remove("view-enter");
  // Force reflow to restart animation
  void viewRoot.offsetWidth;
  viewRoot.classList.add("view-enter");

  const renderFn = routes.get(path);
  if (renderFn) {
    try {
      activeCleanup = renderFn(viewRoot) || null;
    } catch (error) {
      viewRoot.innerHTML = "";
      const errorIcon = icon("monitor");
      viewRoot.appendChild(
        el("div", { class: "empty-state" }, [
          errorIcon,
          el("span", { text: "Failed to load view" }),
          el("span", { text: error.message, style: "font-size:12px;color:var(--text-muted)" }),
        ])
      );
    }
  }
}

export function startRouter(viewRootEl, navRootEl) {
  viewRoot = viewRootEl;
  navLinksRoot = navRootEl;
  window.addEventListener("hashchange", render);
  if (!window.location.hash) window.location.hash = `#${defaultPath()}`;
  render();
}
