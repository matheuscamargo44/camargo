const routes = new Map();
let activeCleanup = null;
let viewRoot = null;
let navLinksRoot = null;

export function registerRoute(path, renderFn) {
  routes.set(path, renderFn);
}

function currentPath() {
  const hash = window.location.hash.replace(/^#/, "");
  return routes.has(hash) ? hash : "/dashboard";
}

function updateActiveNav(path) {
  if (!navLinksRoot) return;
  for (const link of navLinksRoot.querySelectorAll("[data-route]")) {
    link.classList.toggle("active", link.dataset.route === path);
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
  const renderFn = routes.get(path);
  if (renderFn) {
    activeCleanup = renderFn(viewRoot) || null;
  }
}

export function startRouter(viewRootEl, navRootEl) {
  viewRoot = viewRootEl;
  navLinksRoot = navRootEl;
  window.addEventListener("hashchange", render);
  if (!window.location.hash) window.location.hash = "#/dashboard";
  render();
}
