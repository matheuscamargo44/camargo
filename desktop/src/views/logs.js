import { clearLogs, fetchLogs } from "../api.js";
import { el } from "../components.js";
import { icon } from "../icons.js";
import { isLeagueConnected } from "../state.js";

const POLL_MS = 2000;
const LEVEL_ORDER = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };

const FILTERS = [
  { key: "all", label: "All", min: 0 },
  { key: "info", label: "Activity", min: LEVEL_ORDER.INFO },
  { key: "problems", label: "Problems", min: LEVEL_ORDER.WARNING },
];

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour12: false });
}

/** Plain-text rendering — this is what gets pasted somewhere for help. */
function toPlainText(entries) {
  const header = [
    `camargo ${window.camargo.appVersion}`,
    `exported: ${new Date().toISOString()}`,
    `league client: ${isLeagueConnected() ? "detected" : "not detected"}`,
    `entries: ${entries.length}`,
    "",
  ];

  const body = entries.map((entry) => {
    const repeat = entry.count > 1 ? ` (x${entry.count})` : "";
    const line = `${formatTime(entry.ts)} ${entry.level.padEnd(7)} ${entry.source}: ${entry.message}${repeat}`;
    return entry.detail ? `${line}\n${entry.detail}` : line;
  });

  return header.concat(body).join("\n");
}

function entryRow(entry) {
  const meta = el("div", { class: "log-meta" }, [
    el("span", { class: "log-time", text: formatTime(entry.ts) }),
    el("span", { class: `log-level log-level-${entry.level.toLowerCase()}`, text: entry.level }),
    el("span", { class: "log-source", text: entry.source }),
    entry.count > 1 ? el("span", { class: "log-repeat", text: `x${entry.count}` }) : null,
  ]);

  const children = [meta, el("span", { class: "log-message", text: entry.message })];
  if (entry.detail) children.push(el("pre", { class: "log-detail", text: entry.detail }));

  return el("div", { class: `log-entry log-${entry.level.toLowerCase()}` }, children);
}

export function renderLogsView(root) {
  let entries = [];
  let nextSeq = 0;
  let activeFilter = "all";
  let stopped = false;
  let timer = null;

  const status = el("span", { class: "log-status", text: "Loading..." });
  const list = el("div", { class: "log-list" });

  const copyButton = el("button", {
    class: "btn btn-primary",
    text: "Copy log",
    onClick: async () => {
      const visible = visibleEntries();
      if (visible.length === 0) return;
      await window.camargo.copyText(toPlainText(visible));
      copyButton.textContent = `Copied ${visible.length} entries`;
      setTimeout(() => (copyButton.textContent = "Copy log"), 2000);
    },
  });

  const clearButton = el("button", {
    class: "btn btn-secondary",
    text: "Clear",
    onClick: async () => {
      await clearLogs().catch(() => {});
      entries = [];
      nextSeq = 0;
      render();
    },
  });

  const filterWrap = el("div", { class: "log-filters" });
  const filterButtons = FILTERS.map((filter) => {
    const button = el("button", {
      class: `log-filter${filter.key === activeFilter ? " active" : ""}`,
      text: filter.label,
      onClick: () => {
        activeFilter = filter.key;
        for (const [other, node] of filterButtons) node.classList.toggle("active", other === filter.key);
        render();
      },
    });
    filterWrap.appendChild(button);
    return [filter.key, button];
  });

  root.appendChild(
    el("div", { class: "log-toolbar" }, [filterWrap, status, el("div", { class: "log-actions" }, [copyButton, clearButton])])
  );
  root.appendChild(list);

  function visibleEntries() {
    const min = FILTERS.find((f) => f.key === activeFilter).min;
    return entries.filter((entry) => (LEVEL_ORDER[entry.level] ?? 0) >= min);
  }

  function render() {
    const visible = visibleEntries();
    list.innerHTML = "";

    if (visible.length === 0) {
      list.appendChild(
        el("div", { class: "empty-state" }, [icon("monitor"), el("span", { text: "Nothing logged yet." })])
      );
    } else {
      // Oldest first, like a console; the newest line sits at the bottom.
      for (const entry of visible) list.appendChild(entryRow(entry));
    }

    const problems = entries.filter((e) => (LEVEL_ORDER[e.level] ?? 0) >= LEVEL_ORDER.WARNING).length;
    status.textContent = problems
      ? `${entries.length} entries · ${problems} problem${problems === 1 ? "" : "s"}`
      : `${entries.length} entries`;
  }

  async function poll() {
    try {
      const batch = await fetchLogs(nextSeq);
      if (batch.entries.length > 0) {
        const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
        entries = entries.concat(batch.entries);
        nextSeq = batch.next;
        render();
        if (atBottom) list.scrollTop = list.scrollHeight;
      } else if (status.textContent === "Loading...") {
        render();
      }
    } catch {
      status.textContent = "Backend unreachable";
    }
    if (!stopped) timer = setTimeout(poll, POLL_MS);
  }

  poll();

  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}
