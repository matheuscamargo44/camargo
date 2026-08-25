import { el } from "./components.js";

/**
 * Maps an updater state to how the topbar pill should look.
 *
 * Pure and exported so the label/visibility rules are testable without a
 * DOM - two shipped bugs lived exactly here: the pill rendered as an empty
 * capsule before the first state arrived, and it hid itself while idle, so
 * the only way to reach updates was to already have one waiting.
 */
export function describeUpdateState(state, { version, justChecked = false } = {}) {
  const versionLabel = version ? `v${version}` : "Updates";

  switch (state?.status) {
    case "available":
      return {
        label: `Update to ${state.version}`,
        title: `Version ${state.version} is available - click to download`,
        variant: "is-action",
        disabled: false,
      };
    case "downloading":
      return {
        label: `Downloading ${state.percent ?? 0}%`,
        title: "Downloading the update",
        variant: "is-action",
        disabled: true,
      };
    case "ready":
      return {
        label: "Restart to update",
        title: `Version ${state.version} is ready - click to restart and install`,
        variant: "is-ready",
        disabled: false,
      };
    case "error":
      return {
        label: "Update failed",
        title: state.message || "Could not check for updates",
        variant: "is-error",
        disabled: false,
      };
    case "checking":
      return { label: "Checking…", title: "Checking for updates", variant: "", disabled: true };
    case "idle":
    default:
      return {
        label: justChecked ? "Up to date" : versionLabel,
        title: "Click to check for updates",
        variant: "",
        disabled: false,
      };
  }
}

export function mountUpdateIndicator(slot) {
  if (!slot || !window.camargo?.update) return () => {};

  const button = el("button", { class: "update-pill", type: "button" });
  // Hidden until the first state lands, or it flashes as an empty capsule.
  button.hidden = true;
  slot.appendChild(button);

  const version = window.camargo.appVersion;
  let current = { status: "idle" };
  let justChecked = false;

  function render(state) {
    current = state || { status: "idle" };
    const { label, title, variant, disabled } = describeUpdateState(current, { version, justChecked });

    button.hidden = false;
    button.textContent = label;
    button.title = title;
    button.disabled = disabled;
    button.className = variant ? `update-pill ${variant}` : "update-pill";
  }

  button.addEventListener("click", async () => {
    if (current.status === "available") {
      await window.camargo.update.download();
    } else if (current.status === "ready") {
      await window.camargo.update.install();
    } else {
      justChecked = true;
      await window.camargo.update.check();
      // Fall back to the version label, so "Up to date" never becomes the
      // permanent one.
      setTimeout(() => {
        justChecked = false;
        if (current.status === "idle") render(current);
      }, 4000);
    }
  });

  window.camargo.update.onStateChange(render);
  window.camargo.update.getState().then(render).catch(() => render({ status: "idle" }));

  return () => button.remove();
}
