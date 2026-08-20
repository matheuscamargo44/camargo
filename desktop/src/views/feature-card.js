import { callAction, toggleFeature } from "../api.js";
import { actionButton, card, el, inlineForm, statRow, toggleSwitch } from "../components.js";
import { openConfirmModal } from "../modal.js";
import { openIconPicker } from "../icon-picker.js";
import { refreshNow } from "../state.js";
import { formatValue, isBooleanField, STATUS_FIELD_LABELS, statusPill } from "../status-format.js";
import { FEATURE_ACTIONS, FEATURE_TOGGLES } from "./forms.js";

/**
 * Builds a full feature card: title/header, live status rows, one switch
 * per entry in FEATURE_TOGGLES (0, 1, or several), and one control per
 * entry in FEATURE_ACTIONS (inline form, plain button, icon picker, or
 * confirm-then-call for destructive actions). Every feature that has a
 * persistent on/off state gets the same switch treatment — see forms.js.
 */
export function buildFeatureCard(meta, initialStatus) {
  const { cardEl, body } = card({ title: meta.title });

  const statusSection = el("div", { class: "card-status" });
  const togglesSection = el("div", { class: "card-toggles" });
  const controlsSection = el("div", { class: "card-controls" });
  body.appendChild(statusSection);
  body.appendChild(togglesSection);
  body.appendChild(controlsSection);

  // Fields already shown as a switch below don't need to repeat as a status
  // row too — that was making cards taller than they need to be.
  const toggleFields = new Set((FEATURE_TOGGLES[meta.key] || []).map((t) => t.field));

  function renderStatus(status) {
    statusSection.innerHTML = "";
    for (const [field, value] of Object.entries(status || {})) {
      if (field === "key" || toggleFields.has(field)) continue;
      const label = STATUS_FIELD_LABELS[field] || field;
      const row = isBooleanField(field, value)
        ? statRowNode(label, statusPill(field, value))
        : statRow(label, formatValue(value));
      statusSection.appendChild(row);
    }
  }

  renderStatus(initialStatus);

  const toggleButtons = [];
  for (const toggleDef of FEATURE_TOGGLES[meta.key] || []) {
    const { row, button } = buildToggleRow(meta.key, toggleDef, initialStatus);
    toggleButtons.push({ ...toggleDef, button });
    togglesSection.appendChild(row);
  }

  for (const actionDef of FEATURE_ACTIONS[meta.key] || []) {
    controlsSection.appendChild(buildActionControl(meta.key, actionDef));
  }

  return {
    cardEl,
    updateStatus: (status) => {
      renderStatus(status);
      for (const { field, invert, button } of toggleButtons) {
        if (!status || !(field in status)) continue;
        const checked = invert ? !status[field] : Boolean(status[field]);
        button.classList.toggle("switch-on", checked);
        button.classList.toggle("switch-off", !checked);
        button.setAttribute("aria-pressed", String(checked));
      }
    },
  };
}

function statRowNode(label, valueNode) {
  return el("div", { class: "stat-row" }, [el("span", { class: "stat-label", text: label }), valueNode]);
}

function buildToggleRow(key, toggleDef, initialStatus) {
  const checked = toggleDef.invert ? !initialStatus?.[toggleDef.field] : Boolean(initialStatus?.[toggleDef.field]);
  const button = toggleSwitch(checked, async () => {
    button.disabled = true;
    try {
      if (toggleDef.action) {
        await callAction(key, toggleDef.action, {});
      } else {
        await toggleFeature(key);
      }
      await refreshNow();
    } finally {
      button.disabled = false;
    }
  });
  const row = el("div", { class: "card-switch-row" }, [el("span", { text: toggleDef.label }), button]);
  return { row, button };
}

function buildActionControl(key, actionDef) {
  if (actionDef.kind === "icon-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        const iconId = await openIconPicker({ kind: actionDef.iconKind });
        if (iconId === null) return;
        try {
          await callAction(key, actionDef.action, { icon_id: iconId });
          await refreshNow();
        } catch (error) {
          alert(error.message);
        }
      },
      "primary"
    );
  }

  if (actionDef.confirmOnly) {
    return actionButton(
      actionDef.label,
      async () => {
        const confirmed = await openConfirmModal({
          title: actionDef.label,
          description: "Essa ação não pode ser desfeita. Confirmar?",
          confirmLabel: actionDef.label,
        });
        if (!confirmed) return;
        try {
          const result = await callAction(key, actionDef.action, {});
          if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
          await refreshNow();
        } catch (error) {
          alert(error.message);
        }
      },
      "danger"
    );
  }

  if (actionDef.fields.length === 0) {
    return actionButton(
      actionDef.label,
      async () => {
        try {
          const result = await callAction(key, actionDef.action, {});
          if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
          await refreshNow();
        } catch (error) {
          alert(error.message);
        }
      },
      actionDef.quiet ? "secondary" : "primary"
    );
  }

  const wrapper = el("div", { class: "card-action-form" }, [el("p", { class: "card-action-label", text: actionDef.label })]);
  wrapper.appendChild(
    inlineForm({
      fields: actionDef.fields,
      submitLabel: actionDef.label,
      onSubmit: async (values) => {
        await callAction(key, actionDef.action, values);
        await refreshNow();
      },
    })
  );
  return wrapper;
}
