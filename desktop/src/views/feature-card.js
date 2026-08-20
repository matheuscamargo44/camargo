import { callAction, toggleFeature } from "../api.js";
import { openChampionPicker } from "../champion-picker.js";
import { actionButton, card, el, statRow, toggleSwitch } from "../components.js";
import { openConfirmModal, openFormModal } from "../modal.js";
import { openIconPicker } from "../icon-picker.js";
import { openSkinPicker } from "../skin-picker.js";
import { featureIcon } from "../icons.js";
import { isLeagueConnected, onHealthUpdate, refreshNow } from "../state.js";
import { formatSpecialDisplay, formatValue, isBooleanField, isSpecialDisplayField, STATUS_FIELD_LABELS, statusPill } from "../status-format.js";
import { FEATURE_ACTIONS, FEATURE_TOGGLES } from "./forms.js";

/**
 * Builds a full feature card: title/header, live status rows, one switch
 * per entry in FEATURE_TOGGLES (0, 1, or several), and one control per
 * entry in FEATURE_ACTIONS (modal form, plain button, icon picker, or
 * confirm-then-call for destructive actions).
 */
export function buildFeatureCard(meta, initialStatus) {
  const iconEl = featureIcon(meta.key);
  const { cardEl, body } = card({ title: meta.title, iconEl });

  const statusSection = el("div", { class: "card-status" });
  const togglesSection = el("div", { class: "card-toggles" });
  const controlsSection = el("div", { class: "card-controls" });
  body.appendChild(statusSection);
  body.appendChild(togglesSection);
  body.appendChild(controlsSection);

  // Fields already shown as a switch below don't need to repeat as a status row
  const toggleFields = new Set((FEATURE_TOGGLES[meta.key] || []).map((t) => t.field));

  function renderStatus(status) {
    statusSection.innerHTML = "";
    for (const [field, value] of Object.entries(status || {})) {
      if (field === "key" || toggleFields.has(field)) continue;
      const label = STATUS_FIELD_LABELS[field] || field;
      
      let valueNode;
      if (isBooleanField(field, value)) {
        valueNode = statusPill(field, value);
      } else if (isSpecialDisplayField(field, value)) {
        valueNode = formatSpecialDisplay(field, value);
      } else {
        valueNode = formatValue(value);
      }

      const row = typeof valueNode === "string" ? statRow(label, valueNode) : statRowNode(label, valueNode);
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

  const actionButtons = [];
  for (const actionDef of FEATURE_ACTIONS[meta.key] || []) {
    const btn = buildActionControl(meta.key, actionDef);
    actionButtons.push(btn);
    controlsSection.appendChild(btn);
  }

  function applyLeagueState(connected) {
    cardEl.classList.toggle("league-disconnected", !connected);
    for (const { button } of toggleButtons) {
      button.disabled = !connected;
    }
    for (const btn of actionButtons) {
      btn.disabled = !connected;
    }
  }

  applyLeagueState(isLeagueConnected());
  onHealthUpdate((health) => {
    applyLeagueState(Boolean(health?.league_connected));
  });

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
    if (!isLeagueConnected()) return;
    button.disabled = true;
    try {
      if (toggleDef.action) {
        await callAction(key, toggleDef.action, {});
      } else {
        await toggleFeature(key);
      }
      await refreshNow();
    } catch {
      // Ignore
    } finally {
      button.disabled = !isLeagueConnected();
    }
  });
  const row = el("div", { class: "card-switch-row" }, [el("span", { text: toggleDef.label }), button]);
  return { row, button };
}

function buildActionControl(key, actionDef) {
  if (actionDef.kind === "champion-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const champName = await openChampionPicker({
          title: actionDef.pickerTitle || actionDef.label,
          allowNone: actionDef.allowNone !== false,
        });
        if (champName === null) return;
        try {
          await callAction(key, actionDef.action, { [actionDef.paramName || "champion_name"]: champName });
          await refreshNow();
        } catch {
          // Ignore
        }
      },
      "secondary"
    );
  }

  if (actionDef.kind === "skin-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const skinId = await openSkinPicker({ title: actionDef.modalTitle || "Choose Background" });
        if (skinId === null) return;
        try {
          await callAction(key, actionDef.action, { skin_id: skinId });
          await refreshNow();
        } catch {
          // Ignore
        }
      },
      "secondary"
    );
  }

  if (actionDef.kind === "icon-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const iconId = await openIconPicker({ kind: actionDef.iconKind });
        if (iconId === null) return;
        try {
          await callAction(key, actionDef.action, { icon_id: iconId });
          await refreshNow();
        } catch {
          // Ignore
        }
      },
      "secondary"
    );
  }

  if (actionDef.confirmOnly) {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const title = actionDef.modalTitle || actionDef.label;
        const confirmed = await openConfirmModal({
          title,
          description: "This action cannot be undone. Are you sure?",
          confirmLabel: title,
        });
        if (!confirmed) return;
        try {
          const result = await callAction(key, actionDef.action, {});
          if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
          await refreshNow();
        } catch {
          // Ignore
        }
      },
      "danger"
    );
  }

  if (actionDef.fields && actionDef.fields.length > 0) {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const title = actionDef.modalTitle || actionDef.label;
        const values = await openFormModal({
          title,
          fields: actionDef.fields,
          submitLabel: actionDef.label,
        });
        if (!values) return;
        try {
          await callAction(key, actionDef.action, values);
          await refreshNow();
        } catch {
          // Ignore
        }
      },
      "secondary"
    );
  }

  return actionButton(
    actionDef.label,
    async () => {
      if (!isLeagueConnected()) return;
      try {
        const result = await callAction(key, actionDef.action, {});
        if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
        await refreshNow();
      } catch {
        // Ignore
      }
    },
    actionDef.quiet ? "secondary" : "primary"
  );
}
