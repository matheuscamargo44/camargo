export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
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

export function actionButton(label, onClick, tone = "secondary") {
  return el("button", { class: `btn btn-${tone}`, text: label, onClick });
}

export function toggleSwitch(checked, onClick) {
  const button = el("button", {
    class: `switch ${checked ? "switch-on" : "switch-off"}`,
    role: "switch",
    onClick,
  }, [el("span", { class: "switch-knob" })]);
  button.setAttribute("aria-pressed", String(checked));
  return button;
}
