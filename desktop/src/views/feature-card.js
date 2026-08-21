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
  chat_toggle: "Deceive mode (appear offline to friends)",
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
  // Kept so the screen can unsubscribe on teardown: the router throws the DOM
  // away on every route change, and a leaked listener would keep a detached
  // card alive and re-rendered on every poll.
  const unsubscribeHealth = onHealthUpdate((health) => {
    applyLeagueState(Boolean(health?.league_connected));
  });

  return {
    cardEl: rowEl,
    dispose: unsubscribeHealth,
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
    } catch (error) {
      console.error(`toggle ${key} failed:`, error);
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

/**
 * Every action follows the same shape: optionally collect input in a modal,
 * call the backend, refresh. Only the "collect input" step differs, so each
 * kind just provides the params (or null to cancel).
 */
const PARAM_COLLECTORS = {
  "champion-picker": async (actionDef) => {
    const champName = await openChampionPicker({
      title: actionDef.pickerTitle || actionDef.label,
      allowNone: actionDef.allowNone !== false,
    });
    return champName === null ? null : { [actionDef.paramName || "champion_name"]: champName };
  },
  "skin-picker": async (actionDef) => {
    const skinId = await openSkinPicker({ title: actionDef.modalTitle || "Choose Background" });
    return skinId === null ? null : { skin_id: skinId };
  },
  "icon-picker": async (actionDef) => {
    const iconId = await openIconPicker({ kind: actionDef.iconKind });
    return iconId === null ? null : { icon_id: iconId };
  },
  "badge-picker": (actionDef) => openBadgePicker({ title: actionDef.modalTitle || "Change Badges" }),
  "title-picker": (actionDef) =>
    openTitlePicker({ title: actionDef.modalTitle || "Choose Challenge Title" }),
};

async function collectParams(actionDef) {
  const collector = PARAM_COLLECTORS[actionDef.kind];
  if (collector) return collector(actionDef);

  if (actionDef.confirmOnly) {
    const title = actionDef.modalTitle || actionDef.label;
    const confirmed = await openConfirmModal({
      title,
      description: actionDef.description || "Are you sure you want to proceed?",
      confirmLabel: title,
    });
    return confirmed ? {} : null;
  }

  if (actionDef.fields && actionDef.fields.length > 0) {
    const values = await openFormModal({
      title: actionDef.modalTitle || actionDef.label,
      fields: actionDef.fields,
      submitLabel: actionDef.label,
    });
    return values || null;
  }

  return {};
}

function actionTone(actionDef) {
  if (actionDef.confirmOnly) return actionDef.variant || "secondary";
  if (actionDef.kind || (actionDef.fields && actionDef.fields.length > 0)) return "secondary";
  return actionDef.quiet ? "secondary" : "primary";
}

function buildActionControl(key, actionDef) {
  const button = actionButton(
    actionDef.label,
    async () => {
      if (!isLeagueConnected() || button.disabled) return;

      // Bulk actions (disenchanting, mass invites) can run for a while; keep
      // the button from firing twice and show that something is happening.
      button.disabled = true;
      button.classList.add("btn-busy");
      try {
        const params = await collectParams(actionDef);
        if (params === null) return;

        const result = await callAction(key, actionDef.action, params);
        if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
        await refreshNow();
      } catch (error) {
        console.error(`${actionDef.action} on ${key} failed:`, error);
      } finally {
        button.classList.remove("btn-busy");
        button.disabled = !isLeagueConnected();
      }
    },
    actionTone(actionDef)
  );

  return button;
}
