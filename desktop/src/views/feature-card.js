import { callAction, toggleFeature } from "../api.js";
import { openBadgePicker } from "../badge-picker.js";
import { openChampionPicker } from "../champion-picker.js";
import { actionButton, el, toggleSwitch } from "../components.js";
import { openConfirmModal, openFormModal } from "../modal.js";
import { openIconPicker } from "../icon-picker.js";
import { openSkinPicker } from "../skin-picker.js";
import { openTitlePicker } from "../title-picker.js";
import { featureIcon } from "../icons.js";
import { isLeagueConnected, onHealthUpdate, refreshNow } from "../state.js";
import { formatSpecialDisplay, formatValue, isBooleanField, isSpecialDisplayField, STATUS_FIELD_LABELS, statusPill } from "../status-format.js";
import { FEATURE_ACTIONS, FEATURE_TOGGLES } from "./forms.js";

const FEATURE_DESCRIPTIONS = {
  auto_accept: "Accepts match ready checks automatically",
  auto_play_again: "Auto-starts queue in lobby and after matches",
  auto_honor: "Honors teammate automatically post-game",
  random_skin: "Equips random owned skin on champion lock",
  practice_tool: "Custom 5v5 practice match with bots",
  dodge: "Leaves champion select immediately",
  chat: "Deceive mode (appear offline to friends)",
  restart_ux: "Reloads client interface without restarting",
  remove_friends: "Deletes all friends from account",
  status_message: "Custom status message on chat profile",
  badges: "Challenge badges displayed on profile banner",
};

/**
 * Builds a compact, minimalist feature row:
 * [ Icon ]  Title · Status / Description  ─────────  [ Switches / Buttons ]
 */
export function buildFeatureCard(meta, initialStatus) {
  const iconEl = featureIcon(meta.key);

  const rowEl = el("div", { class: "feature-row", "aria-label": meta.title });

  // Left column: Icon + Info (Title & Status/Subtitle)
  const leftEl = el("div", { class: "feature-row-left" });
  const iconWrap = el("div", { class: "feature-row-icon" }, [iconEl]);
  leftEl.appendChild(iconWrap);

  const textWrap = el("div", { class: "feature-row-text" });
  const titleEl = el("span", { class: "feature-row-title", text: meta.title });
  const statusContainer = el("div", { class: "feature-row-status" });
  textWrap.appendChild(titleEl);
  textWrap.appendChild(statusContainer);
  const feedbackEl = el("span", { class: "feature-inline-feedback", style: "display: none;" });
  textWrap.appendChild(feedbackEl);

  let feedbackTimer = null;
  function showFeedback(msg, isError = false) {
    if (feedbackTimer) clearTimeout(feedbackTimer);
    feedbackEl.textContent = `· ${msg}`;
    feedbackEl.style.display = "inline";
    feedbackEl.style.color = isError ? "#f87171" : "#34d399";
    feedbackEl.style.fontSize = "11px";
    feedbackEl.style.fontWeight = "500";
    feedbackTimer = setTimeout(() => {
      feedbackEl.textContent = "";
      feedbackEl.style.display = "none";
    }, 4000);
  }

  // Right column: Switches and Action buttons
  const rightEl = el("div", { class: "feature-row-right" });

  rowEl.appendChild(leftEl);
  rowEl.appendChild(rightEl);

  const toggleDefs = FEATURE_TOGGLES[meta.key] || [];
  const actionDefs = FEATURE_ACTIONS[meta.key] || [];

  function renderStatus(status) {
    statusContainer.innerHTML = "";
    if (!status) {
      if (FEATURE_DESCRIPTIONS[meta.key]) {
        statusContainer.appendChild(el("span", { class: "feature-row-desc", text: FEATURE_DESCRIPTIONS[meta.key] }));
      }
      return;
    }

    const items = [];

    for (const [field, value] of Object.entries(status)) {
      if (field === "key") continue;

      if (isBooleanField(field, value)) {
        items.push(statusPill(field, value));
      } else if (isSpecialDisplayField(field)) {
        items.push(formatSpecialDisplay(field, value));
      } else {
        const label = STATUS_FIELD_LABELS[field] || field;
        const valText = formatValue(field, value);
        items.push(el("span", { class: "feature-status-text", text: `${label}: ${valText}` }));
      }
    }

    if (items.length === 0) {
      if (FEATURE_DESCRIPTIONS[meta.key]) {
        items.push(el("span", { class: "feature-row-desc", text: FEATURE_DESCRIPTIONS[meta.key] }));
      } else {
        items.push(el("span", { class: "feature-status-muted", text: "Ready" }));
      }
    }

    for (const item of items) {
      statusContainer.appendChild(item);
    }
  }

  // Build controls (right side)
  const switchesWrap = el("div", { class: "row-switches-group" });
  for (const toggleDef of toggleDefs) {
    const { element, button } = buildToggleControl(meta.key, toggleDef);
    switchesWrap.appendChild(element);

    if (initialStatus) {
      const initialVal = toggleDef.field
        ? Boolean(initialStatus[toggleDef.field])
        : Boolean(initialStatus.enabled);
      button.setAttribute("aria-checked", String(initialVal));
      button.classList.toggle("active", initialVal);
    }
  }
  if (toggleDefs.length > 0) rightEl.appendChild(switchesWrap);

  const actionsWrap = el("div", { class: "row-actions-group" });
  for (const actionDef of actionDefs) {
    actionsWrap.appendChild(buildActionControl(meta.key, actionDef, showFeedback));
  }
  if (actionDefs.length > 0) rightEl.appendChild(actionsWrap);

  renderStatus(initialStatus);

  function applyLeagueState(connected) {
    rowEl.classList.toggle("league-disconnected", !connected);
  }

  applyLeagueState(isLeagueConnected());
  onHealthUpdate((health) => {
    applyLeagueState(Boolean(health?.league_connected));
  });

  return {
    cardEl: rowEl,
    element: rowEl,
    updateStatus(status) {
      renderStatus(status);
      if (!status) return;

      const buttons = rightEl.querySelectorAll(".switch-button");
      toggleDefs.forEach((def, index) => {
        const val = def.field ? Boolean(status[def.field]) : Boolean(status.enabled);
        const btn = buttons[index];
        if (btn) {
          btn.setAttribute("aria-checked", String(val));
          btn.classList.toggle("active", val);
        }
      });
    },
    update(status) {
      this.updateStatus(status);
    },
  };
}

function buildToggleControl(key, toggleDef) {
  const isEnabled = false;
  const button = toggleSwitch(isEnabled, async (btn) => {
    if (!isLeagueConnected()) return;
    const currentState = btn.getAttribute("aria-checked") === "true";
    const nextState = !currentState;
    btn.setAttribute("aria-checked", String(nextState));
    btn.classList.toggle("active", nextState);

    try {
      if (toggleDef.action) {
        await callAction(key, toggleDef.action, { state: nextState });
      } else {
        await toggleFeature(key);
      }
      await refreshNow();
    } catch {
      btn.setAttribute("aria-checked", String(currentState));
      btn.classList.toggle("active", currentState);
    }
  });

  if (toggleDef.label) {
    const element = el("div", { class: "row-switch-labeled" }, [
      el("span", { class: "row-switch-label", text: toggleDef.label }),
      button,
    ]);
    return { element, button };
  }

  return { element: button, button };
}

function buildActionControl(key, actionDef, showFeedback = () => {}) {
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
          showFeedback("Updated");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
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
          showFeedback("Applied");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
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
          showFeedback("Applied");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
        }
      },
      "secondary"
    );
  }

  if (actionDef.kind === "badge-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const result = await openBadgePicker({ title: actionDef.modalTitle || "Change Badges" });
        if (result === null) return;
        try {
          await callAction(key, actionDef.action, result);
          showFeedback("Updated");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
        }
      },
      "secondary"
    );
  }

  if (actionDef.kind === "title-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const result = await openTitlePicker({ title: actionDef.modalTitle || "Choose Challenge Title" });
        if (result === null) return;
        try {
          await callAction(key, actionDef.action, result);
          showFeedback("Updated");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
        }
      },
      "secondary"
    );
  }

  if (actionDef.confirmOnly) {
    const variant = actionDef.variant || "secondary";
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const title = actionDef.modalTitle || actionDef.label;
        const confirmed = await openConfirmModal({
          title,
          description: actionDef.description || "Are you sure you want to proceed?",
          confirmLabel: title,
        });
        if (!confirmed) return;
        try {
          const result = await callAction(key, actionDef.action, {});
          if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
          showFeedback("Done");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
        }
      },
      variant
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
          showFeedback("Saved");
          await refreshNow();
        } catch (err) {
          showFeedback(err.message || "Failed", true);
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
        showFeedback("Done");
        await refreshNow();
      } catch (err) {
        showFeedback(err.message || "Failed", true);
      }
    },
    actionDef.quiet ? "secondary" : "primary"
  );
}
