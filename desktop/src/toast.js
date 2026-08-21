import { el } from "./components.js";

const MAX_VISIBLE = 4;
const DISMISS_MS = { error: 6000, warn: 5000, success: 3500, info: 3500 };

let containerEl = null;

function container() {
  if (containerEl) return containerEl;
  containerEl = el("div", { id: "toast-stack", role: "status", "aria-live": "polite" });
  document.body.appendChild(containerEl);
  return containerEl;
}

function dismiss(toastEl) {
  if (!toastEl.isConnected || toastEl.dataset.leaving) return;
  toastEl.dataset.leaving = "true";
  toastEl.classList.add("toast-leaving");
  toastEl.addEventListener("animationend", () => toastEl.remove(), { once: true });
  // Fallback if the animation never runs (reduced motion, hidden window)
  setTimeout(() => toastEl.remove(), 400);
}

/**
 * Shows a transient message. `level` is one of info | success | warn | error,
 * matching the levels the backend emits on the event stream.
 */
export function showToast(level, message) {
  if (!message) return;

  const stack = container();
  // `text` (not `html`): messages carry summoner names and backend strings
  const toastEl = el("div", { class: `toast toast-${level}` }, [
    el("span", { class: "toast-message", text: String(message) }),
  ]);
  toastEl.onclick = () => dismiss(toastEl);

  stack.appendChild(toastEl);
  while (stack.childElementCount > MAX_VISIBLE) dismiss(stack.firstElementChild);

  setTimeout(() => dismiss(toastEl), DISMISS_MS[level] ?? DISMISS_MS.info);
  return toastEl;
}

/** Convenience wrapper for a failed action. */
export function showError(error) {
  showToast("error", error?.message || "Something went wrong");
}
