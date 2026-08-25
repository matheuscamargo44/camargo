import { el } from "./components.js";

/**
 * Topbar control for in-app updates. Hidden entirely unless there is
 * something to say - an always-visible "you're up to date" badge is noise
 * on every launch.
 */
export function mountUpdateIndicator(slot) {
  if (!slot || !window.camargo?.update) return () => {};

  const button = el("button", { class: "update-pill", type: "button" });
  slot.appendChild(button);

  let current = { status: "idle" };

  function render(state) {
    current = state || { status: "idle" };
    const { status, version, percent, message } = current;

    button.classList.remove("is-ready", "is-error");
    button.disabled = false;
    button.hidden = false;

    switch (status) {
      case "available":
        button.textContent = `Update to ${version}`;
        button.title = `Version ${version} is available - click to download`;
        break;
      case "downloading":
        button.textContent = `Downloading ${percent}%`;
        button.title = "Downloading the update";
        button.disabled = true;
        break;
      case "ready":
        button.textContent = "Restart to update";
        button.title = `Version ${version} is ready - click to restart and install`;
        button.classList.add("is-ready");
        break;
      case "error":
        button.textContent = "Update failed";
        button.title = message || "Could not check for updates";
        button.classList.add("is-error");
        break;
      case "checking":
      case "idle":
      default:
        // Nothing worth a button: stay out of the way.
        button.hidden = true;
        break;
    }
  }

  button.addEventListener("click", async () => {
    if (current.status === "available") {
      await window.camargo.update.download();
    } else if (current.status === "ready") {
      await window.camargo.update.install();
    } else if (current.status === "error") {
      await window.camargo.update.check();
    }
  });

  window.camargo.update.onStateChange(render);
  window.camargo.update.getState().then(render).catch(() => {});

  return () => button.remove();
}
