import { callAction, toggleFeature } from "../api.js";
import { actionButton, card, el, inlineForm, statRow, toggleSwitch } from "../components.js";
import { openConfirmModal } from "../modal.js";
import { refreshNow } from "../state.js";
import { FEATURE_ACTIONS } from "./forms.js";

const TOGGLEABLE_FEATURES = new Set(["auto_accept", "ragequeue", "chat_toggle"]);

const STATUS_FIELD_LABELS = {
  enabled: "Ativo",
  instalock_enabled: "Instalock",
  instalock_champion: "Campeão (instalock)",
  autoban_enabled: "AutoBan",
  autoban_champion: "Campeão (autoban)",
  queue_id: "Fila (ID)",
  queue_name: "Fila",
  first_position: "1ª posição",
  second_position: "2ª posição",
  provider: "Provedor",
  disconnected: "Chat desconectado",
};

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  return String(value);
}

/**
 * Builds a full feature card: title/category header, live status rows, an
 * on/off switch when the feature supports it, and one control per entry in
 * FEATURE_ACTIONS (inline form, plain button, or confirm-then-call for
 * destructive actions).
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
      statusSection.appendChild(statRow(STATUS_FIELD_LABELS[field] || field, formatValue(value)));
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

function buildActionControl(key, actionDef) {
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
