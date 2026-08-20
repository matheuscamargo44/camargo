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
  leftEl.appendChild(textWrap);

  // Right column: Switches and Action buttons
  const rightEl = el("div", { class: "feature-row-right" });

  rowEl.appendChild(leftEl);
  rowEl.appendChild(rightEl);

  const toggleDefs = FEATURE_TOGGLES[meta.key] || [];
  const actionDefs = FEATURE_ACTIONS[meta.key] || [];
  const toggleFields = new Set(toggleDefs.map((t) => t.field));

  function renderStatus(status) {
    statusContainer.innerHTML = "";
    if (!status) {
      if (FEATURE_DESCRIPTIONS[meta.key]) {
        statusContainer.appendChild(el("span", { class: "feature-row-desc", text: FEATURE_DESCRIPTIONS[meta.key] }));
      }
      return;
    }

    // Special formatted status for Loot & Crafting
    if (meta.key === "mass_disenchant") {
      const frag = status.key_fragments ?? 0;
      const chests = status.chests ?? 0;
      const shards = status.total_shards ?? 0;
      const text = `${frag} Keys · ${chests} Chests · ${shards} Shards`;
      statusContainer.appendChild(el("span", { class: "feature-status-text", text }));
      return;
    }

    // Special formatted status for Instalock
    if (meta.key === "instalock") {
      const champ = status.instalock_champion || status.champion || "None";
      statusContainer.appendChild(formatSpecialDisplay("instalock_champion", champ));
      return;
    }

    // Special formatted status for AutoBan
    if (meta.key === "autoban") {
      const champ = status.autoban_champion || status.champion || "None";
      statusContainer.appendChild(formatSpecialDisplay("autoban_champion", champ));
      return;
    }

    // Special formatted status for ARAM Bench Swap
    if (meta.key === "aram_bench_swap") {
      const champ = status.target_champion || status.champion || "None";
      statusContainer.appendChild(formatSpecialDisplay("target_champion", champ));
      return;
    }

    const items = [];

    for (const [field, value] of Object.entries(status)) {
      if (field === "key" || toggleFields.has(field)) continue;
      if (value === null || value === undefined || value === "") continue;

      const label = STATUS_FIELD_LABELS[field] || field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

      if (isSpecialDisplayField(field, value)) {
        const specialNode = formatSpecialDisplay(field, value);
        items.push(el("div", { class: "feature-status-item" }, [
          el("span", { class: "feature-status-label", text: `${label}:` }),
          specialNode,
        ]));
      } else if (typeof value === "boolean") {
        items.push(statusPill(field, value));
      } else {
        const formatted = formatValue(value);
        if (formatted) {
          items.push(el("span", { class: "feature-status-text", text: `${label}: ${formatted}` }));
        }
      }
    }

    if (items.length > 0) {
      for (const item of items) {
        statusContainer.appendChild(item);
      }
    } else if (FEATURE_DESCRIPTIONS[meta.key]) {
      statusContainer.appendChild(el("span", { class: "feature-row-desc", text: FEATURE_DESCRIPTIONS[meta.key] }));
    }
  }

  renderStatus(initialStatus);

  // Build Toggles
  const toggleButtons = [];
  for (const toggleDef of toggleDefs) {
    const { element, button } = buildToggleControl(meta.key, toggleDef, initialStatus, toggleDefs.length > 1);
    toggleButtons.push({ ...toggleDef, button });
    rightEl.appendChild(element);
  }

  // Build Action Buttons
  const actionButtons = [];
  for (const actionDef of actionDefs) {
    const btn = buildActionControl(meta.key, actionDef);
    actionButtons.push(btn);
    rightEl.appendChild(btn);
  }

  function applyLeagueState(connected) {
    rowEl.classList.toggle("league-disconnected", !connected);
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
    cardEl: rowEl,
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

function buildToggleControl(key, toggleDef, initialStatus, showLabel = false) {
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

  if (showLabel) {
    const element = el("div", { class: "row-switch-labeled" }, [
      el("span", { class: "row-switch-label", text: toggleDef.label }),
      button,
    ]);
    return { element, button };
  }

  return { element: button, button };
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

  if (actionDef.kind === "badge-picker") {
    return actionButton(
      actionDef.label,
      async () => {
        if (!isLeagueConnected()) return;
        const result = await openBadgePicker({ title: actionDef.modalTitle || "Change Badges" });
        if (result === null) return;
        try {
          await callAction(key, actionDef.action, result);
          await refreshNow();
        } catch {
          // Ignore
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
          await refreshNow();
        } catch {
          // Ignore
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
          await refreshNow();
        } catch {
          // Ignore
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

