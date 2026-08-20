let overlayEl = null;
let closeCallback = null;

function ensureOverlay() {
  if (overlayEl) return overlayEl;
  overlayEl = document.createElement("div");
  overlayEl.className = "modal-overlay";
  overlayEl.setAttribute("role", "dialog");
  overlayEl.setAttribute("aria-modal", "true");
  overlayEl.onclick = (event) => {
    if (event.target === overlayEl) closeModal();
  };
  document.body.appendChild(overlayEl);
  return overlayEl;
}

function onKeyDown(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    closeModal();
  }
  // Focus trap
  if (event.key === "Tab" && overlayEl && !overlayEl.hidden) {
    const focusable = overlayEl.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey) {
      if (document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }
}

/**
 * Opens the shared modal overlay with animated transition.
 * Returns the overlay element to append content into.
 * Pass a `onClose` callback that will be called when the modal is dismissed.
 */
export function openOverlay(onClose) {
  const overlay = ensureOverlay();
  overlay.innerHTML = "";
  overlay.hidden = false;
  closeCallback = onClose || null;

  // Trigger animation on next frame
  requestAnimationFrame(() => {
    overlay.classList.add("modal-visible");
  });

  document.addEventListener("keydown", onKeyDown);
  return overlay;
}

export function closeModal() {
  if (!overlayEl) return;

  overlayEl.classList.remove("modal-visible");

  const cb = closeCallback;
  closeCallback = null;

  const onEnd = () => {
    overlayEl.removeEventListener("transitionend", onEnd);
    overlayEl.hidden = true;
    overlayEl.innerHTML = "";
    document.removeEventListener("keydown", onKeyDown);
    if (typeof cb === "function") cb();
  };

  overlayEl.addEventListener("transitionend", onEnd);

  // Fallback in case transitionend doesn't fire
  setTimeout(onEnd, 400);
}

function buildField(field) {
  const wrapper = document.createElement("label");
  wrapper.className = "modal-field";

  const labelText = document.createElement("span");
  labelText.textContent = field.label;
  wrapper.appendChild(labelText);

  let input;
  if (field.type === "select") {
    input = document.createElement("select");
    for (const option of field.options) {
      const optionEl = document.createElement("option");
      optionEl.value = option.value;
      optionEl.textContent = option.label;
      if (field.value !== undefined && String(option.value) === String(field.value)) {
        optionEl.selected = true;
      }
      input.appendChild(optionEl);
    }
  } else {
    input = document.createElement("input");
    input.type = field.type || "text";
    if (field.value !== undefined && field.value !== null) {
      input.value = field.value;
    }
  }
  input.name = field.name;
  if (field.placeholder) input.placeholder = field.placeholder;
  wrapper.appendChild(input);

  return wrapper;
}

/**
 * Opens a modal built from a field list. Resolves with the field values
 * (object) when submitted, or null when cancelled.
 */
export function openFormModal({ title, description, fields = [], submitLabel = "Confirm" }) {
  return new Promise((resolve) => {
    let resolved = false;

    function finish(value) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(value);
    }

    const overlay = openOverlay(() => {
      // Called when modal is closed without submitting
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    });

    const box = document.createElement("div");
    box.className = "modal-box";

    const heading = document.createElement("h2");
    heading.textContent = title;
    box.appendChild(heading);

    if (description) {
      const desc = document.createElement("p");
      desc.className = "modal-description";
      desc.textContent = description;
      box.appendChild(desc);
    }

    const form = document.createElement("form");
    for (const field of fields) {
      form.appendChild(buildField(field));
    }

    const errorEl = document.createElement("p");
    errorEl.className = "modal-error";
    errorEl.hidden = true;
    form.appendChild(errorEl);

    const actions = document.createElement("div");
    actions.className = "modal-actions";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.onclick = () => finish(null);

    const submitButton = document.createElement("button");
    submitButton.type = "submit";
    submitButton.className = "primary";
    submitButton.textContent = submitLabel;

    actions.appendChild(cancelButton);
    actions.appendChild(submitButton);
    form.appendChild(actions);

    form.onsubmit = (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      finish(data);
    };

    box.appendChild(form);
    overlay.appendChild(box);

    const firstInput = form.querySelector("input, select");
    if (firstInput) firstInput.focus();
  });
}

export function openConfirmModal({ title, description, confirmLabel = "Confirm" }) {
  return openFormModal({ title, description, fields: [], submitLabel: confirmLabel }).then(
    (result) => result !== null
  );
}
