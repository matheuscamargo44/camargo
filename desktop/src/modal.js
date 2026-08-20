let overlayEl = null;

function ensureOverlay() {
  if (overlayEl) return overlayEl;
  overlayEl = document.createElement("div");
  overlayEl.className = "modal-overlay";
  overlayEl.hidden = true;
  overlayEl.onclick = (event) => {
    if (event.target === overlayEl) closeModal();
  };
  document.body.appendChild(overlayEl);
  return overlayEl;
}

export function closeModal() {
  if (overlayEl) {
    overlayEl.hidden = true;
    overlayEl.innerHTML = "";
  }
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
      input.appendChild(optionEl);
    }
  } else {
    input = document.createElement("input");
    input.type = field.type || "text";
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
export function openFormModal({ title, description, fields = [], submitLabel = "Confirmar" }) {
  return new Promise((resolve) => {
    const overlay = ensureOverlay();
    overlay.innerHTML = "";
    overlay.hidden = false;

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
    cancelButton.textContent = "Cancelar";
    cancelButton.onclick = () => {
      closeModal();
      resolve(null);
    };

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
      closeModal();
      resolve(data);
    };

    box.appendChild(form);
    overlay.appendChild(box);

    const firstInput = form.querySelector("input, select");
    if (firstInput) firstInput.focus();
  });
}

export function openConfirmModal({ title, description, confirmLabel = "Confirmar" }) {
  return openFormModal({ title, description, fields: [], submitLabel: confirmLabel }).then(
    (result) => result !== null
  );
}
