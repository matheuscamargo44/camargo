import { callAction, reportClientError, toggleFeature } from "../api.js";
import { openAgentPicker } from "../agent-picker.js";
import { openBadgePicker } from "../badge-picker.js";
import { openChampionListEditor } from "../champion-list-editor.js";
import { openChampionPicker } from "../champion-picker.js";
import { actionButton, el, toggleSwitch } from "../components.js";
import { openConfirmModal, openFormModal } from "../modal.js";
import { openIconPicker } from "../icon-picker.js";
import { openModePicker } from "../mode-picker.js";
import { openSkinPicker } from "../skin-picker.js";
import { openTitlePicker } from "../title-picker.js";
import { featureIcon } from "../icons.js";
import { isFeatureConnected, onHealthUpdate, refreshNow } from "../state.js";
import { formatSpecialDisplay, formatValue, isBooleanField, isSpecialDisplayField, STATUS_FIELD_LABELS, statusPill } from "../status-format.js";
import { getAgentIcon, getAgentIconsMap, getRankTierInfo, getRankTiersMap } from "../valorant-data.js";
import { FEATURE_ACTIONS, FEATURE_TOGGLES } from "./forms.js";

/** Agent portrait + name (+ optional region suffix), mirroring the champion
 * pill League's Instalock card uses — same lazy-resolve-then-backfill trick,
 * just against valorant-api.com instead of Data Dragon.
 */
function buildAgentPill(agentName, suffix = "") {
  const iconUrl = getAgentIcon(agentName);
  const img = el("img", { src: iconUrl, class: "stat-champ-thumb", alt: agentName });
  if (!iconUrl) img.style.display = "none";
  img.onerror = () => { img.style.display = "none"; };
  const labelSpan = el("span", { text: `${agentName}${suffix}` });
  const pill = el("div", { class: "stat-champ-pill" }, [img, labelSpan]);

  if (!iconUrl) {
    getAgentIconsMap().then((map) => {
      const updated = map[agentName.toLowerCase()];
      if (updated) {
        img.src = updated;
        img.style.display = "";
      }
    });
  }

  return pill;
}

/** Tier icon + name + RR, e.g. "Diamond 2 · 11 RR". Resolves the icon/name
 * lazily from the public tier list the same way status-format.js resolves
 * League skin names — render with whatever's cached, then backfill.
 */
function buildRankPill(tier, rr) {
  const info = getRankTierInfo(tier);
  const labelText = info ? `${info.name}${rr != null ? ` · ${rr} RR` : ""}` : `Tier ${tier}`;
  const img = el("img", { src: info?.icon || "", class: "stat-champ-thumb", alt: labelText });
  if (!info?.icon) img.style.display = "none";
  img.onerror = () => { img.style.display = "none"; };
  const labelSpan = el("span", { text: labelText });
  const pill = el("div", { class: "stat-champ-pill" }, [img, labelSpan]);

  if (!info) {
    getRankTiersMap().then((map) => {
      const updated = map[tier];
      if (updated) {
        if (updated.icon) {
          img.src = updated.icon;
          img.style.display = "";
        }
        labelSpan.textContent = `${updated.name}${rr != null ? ` · ${rr} RR` : ""}`;
      }
    });
  }

  return pill;
}

/** Champion priority list as a row of pills (or "None" when empty). */
function buildChampionListDisplay(field, names) {
  const list = Array.isArray(names) ? names.filter(Boolean) : names && names !== "None" ? [names] : [];
  if (list.length === 0) {
    return el("span", { text: "None" });
  }
  const wrap = el("div", { class: "champ-list-pills" });
  for (const name of list) {
    wrap.appendChild(formatSpecialDisplay(field, name));
  }
  return wrap;
}

const FEATURE_DESCRIPTIONS = {
  auto_accept: "Accepts match ready checks automatically",
  auto_play_again: "Auto-starts queue in lobby and after matches",
  auto_honor: "Honors teammate automatically post-game",
  random_skin: "Equips random owned skin on champion lock",
  dodge: "Leaves champion select immediately",
  chat_toggle: "Deceive mode (appear offline to friends)",
  restart_ux: "Reloads client interface without restarting",
  remove_friends: "Deletes all friends from account",
  status_message: "Custom status message on chat profile",
  badges: "Challenge badges displayed on profile banner",
  valorant_dodge: "Leaves agent select immediately",
  valorant_chat_toggle: "Deceive mode (appear offline to friends)",
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

    // Special formatted status for Instalock (priority list, tried in order)
    if (meta.key === "instalock") {
      statusContainer.appendChild(buildChampionListDisplay("instalock_champion", status.instalock_champion));
      return;
    }

    // Special formatted status for AutoBan (priority list, tried in order)
    if (meta.key === "autoban") {
      statusContainer.appendChild(buildChampionListDisplay("autoban_champion", status.autoban_champion));
      return;
    }

    // Special formatted status for Aram Bench Swap (priority list, tried in order)
    if (meta.key === "aram_bench_swap") {
      statusContainer.appendChild(buildChampionListDisplay("target_champion", status.target_champion));
      return;
    }

    // Special formatted status for VALORANT Instalock
    if (meta.key === "valorant_instalock") {
      const agent = status.instalock_agent || "None";
      const region = status.region && status.region !== "auto" ? ` · ${status.region.toUpperCase()}` : "";
      if (agent.toLowerCase() === "none") {
        statusContainer.appendChild(el("span", { text: "None" }));
      } else {
        statusContainer.appendChild(buildAgentPill(agent, region));
      }
      return;
    }

    // Special formatted status for VALORANT Rank (combines tier + RR into
    // one pill instead of two separate lines)
    if (meta.key === "valorant_rank") {
      if (status.tier === null || status.tier === undefined) {
        statusContainer.appendChild(el("span", { class: "feature-row-desc", text: "Rank unavailable" }));
        return;
      }
      statusContainer.appendChild(buildRankPill(status.tier, status.rr));
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
    const { element, button } = buildToggleControl(meta.key, toggleDef, initialStatus, toggleDefs.length > 1, meta.game);
    toggleButtons.push({ ...toggleDef, button });
    rightEl.appendChild(element);
  }

  // Build Action Buttons
  const actionButtons = [];
  for (const actionDef of actionDefs) {
    const btn = buildActionControl(meta.key, actionDef, meta.game);
    actionButtons.push(btn);
    rightEl.appendChild(btn);
  }

  function applyConnectionState(connected) {
    rowEl.classList.toggle("league-disconnected", !connected);
    for (const { button } of toggleButtons) {
      button.disabled = !connected;
    }
    for (const btn of actionButtons) {
      btn.disabled = !connected;
    }
  }

  applyConnectionState(isFeatureConnected(meta.game));
  // Kept so the screen can unsubscribe on teardown: the router throws the DOM
  // away on every route change, and a leaked listener would keep a detached
  // card alive and re-rendered on every poll.
  const unsubscribeHealth = onHealthUpdate(() => {
    applyConnectionState(isFeatureConnected(meta.game));
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

function buildToggleControl(key, toggleDef, initialStatus, showLabel = false, game) {
  const checked = toggleDef.invert ? !initialStatus?.[toggleDef.field] : Boolean(initialStatus?.[toggleDef.field]);
  const button = toggleSwitch(checked, async () => {
    if (!isFeatureConnected(game)) return;
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
      reportClientError(`Toggling ${key} failed: ${error.message}`, error.stack, "toggle");
    } finally {
      button.disabled = !isFeatureConnected(game);
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
  "agent-picker": async (actionDef) => {
    const agentName = await openAgentPicker({
      title: actionDef.pickerTitle || actionDef.label,
      allowNone: actionDef.allowNone !== false,
    });
    return agentName === null ? null : { [actionDef.paramName || "agent_name"]: agentName };
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

function buildActionControl(key, actionDef, game) {
  const button = actionButton(
    actionDef.label,
    async () => {
      if (!isFeatureConnected(game) || button.disabled) return;

      // Bulk actions (disenchanting, mass invites) can run for a while; keep
      // the button from firing twice and show that something is happening.
      button.disabled = true;
      button.classList.add("btn-busy");
      try {
        if (actionDef.kind === "champion-list-editor") {
          const changed = await openChampionListEditor({
            featureKey: key,
            statusField: actionDef.statusField,
            modalTitle: actionDef.modalTitle,
          });
          if (changed) await refreshNow();
          return;
        }

        if (actionDef.kind === "mode-picker") {
          const changed = await openModePicker({ featureKey: key, modalTitle: actionDef.modalTitle });
          if (changed) await refreshNow();
          return;
        }

        const params = await collectParams(actionDef);
        if (params === null) return;

        const result = await callAction(key, actionDef.action, params);
        if (actionDef.opensUrl && result.result) window.open(result.result, "_blank");
        await refreshNow();
      } catch (error) {
        console.error(`${actionDef.action} on ${key} failed:`, error);
        reportClientError(
          `Action ${actionDef.action} on ${key} failed: ${error.message}`,
          error.stack,
          "action"
        );
      } finally {
        button.classList.remove("btn-busy");
        button.disabled = !isFeatureConnected(game);
      }
    },
    actionTone(actionDef)
  );

  return button;
}
