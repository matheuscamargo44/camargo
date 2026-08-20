import { callAction, toggleFeature } from "../api.js";
import { actionButton, card, el, inlineForm, statRow, toggleSwitch } from "../components.js";
import { openConfirmModal } from "../modal.js";
import { openIconPicker } from "../icon-picker.js";
import { refreshNow } from "../state.js";
import { formatValue, isBooleanField, STATUS_FIELD_LABELS, statusPill } from "../status-format.js";
import { FEATURE_ACTIONS } from "./forms.js";

const TOGGLEABLE_FEATURES = new Set(["auto_accept", "ragequeue", "chat_toggle"]);

/**
 * Builds a full feature card: title/category header, live status rows, an
 * on/off switch when the feature supports it, and one control per entry in
 * FEATURE_ACTIONS (inline form, plain button, icon picker, or
 * confirm-then-call for destructive actions).
 */
export function buildFeatureCard(meta, initialStatus) {
  const { cardEl, body } = card({ title: meta.title });

  const statusSection = el("div", { class: "card-status" });
  const controlsSection = el("div", { class: "card-controls" });
  body.appendChild(statusSection);
  body.appendChild(controlsSection);

  function renderStatus(status) {
    statusSection.innerHTML = "";
    for (const [field, value] of Object.entries(status || {})) {
      if (field === "key") continue;
      const label = STATUS_FIELD_LABELS[field] || field;
      const row = isBooleanField(field, value)
        ? statRowNode(label, statusPill(field, value))
        : statRow(label, formatValue(value));
      statusSection.appendChild(row);
    }
  }

  renderStatus(initialStatus);

  if (TOGGLEABLE_FEATURES.has(meta.key)) {
    const switchRow = el("div", { class: "card-switch-row" }, [
      el("span", { text: "Ligado" }),
    ]);
    const button = toggleSwitch(Boolean(initialStatus?.enabled), async () => {
      button.disabled = true;
      try {
        await toggleFeature(meta.key);
        await refreshNow();
      } finally {
        button.disabled = false;
      }
    });
    switchRow.appendChild(button);
    controlsSection.appendChild(switchRow);
  }

  for (const actionDef of FEATURE_ACTIONS[meta.key] || []) {
    controlsSection.appendChild(buildActionControl(meta.key, actionDef));
  }

  return {
    cardEl,
    updateStatus: (status) => {
      renderStatus(status);
      const button = controlsSection.querySelector(".switch");
      if (button && status && "enabled" in status) {
        button.classList.toggle("switch-on", Boolean(status.enabled));
        button.classList.toggle("switch-off", !status.enabled);
        button.setAttribute("aria-pressed", String(Boolean(status.enabled)));
      }
    },
  };
}

function statRowNode(label, valueNode) {
  return el("div", { class: "stat-row" }, [el("span", { class: "stat-label", text: label }), valueNode]);
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
