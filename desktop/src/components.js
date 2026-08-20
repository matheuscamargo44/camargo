export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value !== undefined && value !== null) {
      node.setAttribute(key, value);
    }
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

export function card({ title, subtitle }) {
  const header = el("div", { class: "card-header" }, [
    el("h3", { text: title }),
    subtitle ? el("p", { class: "card-subtitle", text: subtitle }) : null,
  ]);
  const body = el("div", { class: "card-body" });
  const cardEl = el("section", { class: "card" }, [header, body]);
  return { cardEl, body };
}

function buildField(field) {
  const wrapper = el("label", { class: "field" }, [el("span", { text: field.label })]);
  let input;
  if (field.type === "select") {
    input = el(
      "select",
      { name: field.name },
      field.options.map((opt) => el("option", { value: opt.value, text: opt.label }))
    );
  } else if (field.type === "textarea") {
    input = el("textarea", { name: field.name, rows: field.rows || 2, placeholder: field.placeholder || "" });
  } else {
    input = el("input", {
      name: field.name,
      type: field.type || "text",
      placeholder: field.placeholder || "",
    });
  }
  wrapper.appendChild(input);
  return wrapper;
}

/**
 * Builds an inline form (used directly inside a screen, not a modal).
 * Returns the form element; call form.reset() manually if desired.
 */
export function inlineForm({ fields = [], submitLabel = "Aplicar", onSubmit, tone = "primary" }) {
  const form = el("form", { class: "inline-form" });
  for (const field of fields) form.appendChild(buildField(field));

  const errorEl = el("p", { class: "field-error" });
  errorEl.hidden = true;

  const submitButton = el("button", { type: "submit", class: `btn btn-${tone}`, text: submitLabel });
  const actions = el("div", { class: "inline-form-actions" }, [submitButton]);

  form.appendChild(errorEl);
  form.appendChild(actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    const values = Object.fromEntries(new FormData(form).entries());
    submitButton.disabled = true;
    try {
      await onSubmit(values);
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
    } finally {
      submitButton.disabled = false;
    }
  });

  return form;
}

export function actionButton(label, onClick, tone = "secondary") {
  return el("button", { class: `btn btn-${tone}`, text: label, onClick });
}

export function toggleSwitch(checked, onClick) {
  const button = el("button", {
    class: `switch ${checked ? "switch-on" : "switch-off"}`,
    onClick,
  }, [el("span", { class: "switch-knob" })]);
  button.setAttribute("aria-pressed", String(checked));
  return button;
}

export function statRow(label, valueText) {
  return el("div", { class: "stat-row" }, [el("span", { class: "stat-label", text: label }), el("span", { class: "stat-value", text: valueText })]);
}
