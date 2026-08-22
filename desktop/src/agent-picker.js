import { el } from "./components.js";
import { openOverlay, closeModal } from "./modal.js";

const AGENTS_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true";

let cachedAgents = null; // [{ name, imgUrl }]

async function loadAgents() {
  if (cachedAgents) return cachedAgents;

  const data = await fetch(AGENTS_URL).then((r) => r.json());

  cachedAgents = (data.data || [])
    .map((agent) => ({
      name: agent.displayName,
      imgUrl: agent.displayIconSmall || agent.displayIcon,
    }))
    .filter((agent) => agent.name)
    .sort((a, b) => a.name.localeCompare(b.name));

  return cachedAgents;
}

function renderAgentGrid(gridEl, agents, onPick, { allowNone = true, query = "" }) {
  gridEl.innerHTML = "";

  const q = query.trim().toLowerCase();

  if (allowNone && (!q || "none".includes(q))) {
    const noneBtn = el("button", {
      type: "button",
      class: "champ-picker-item champ-picker-special",
      title: "None (Disabled)",
      onClick: () => onPick("None"),
    }, [
      el("div", { class: "champ-picker-special-icon" }, [
        el("svg", {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          "stroke-width": "2",
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
        }, [
          el("circle", { cx: "12", cy: "12", r: "10" }),
          el("line", { x1: "4.93", y1: "4.93", x2: "19.07", y2: "19.07" }),
        ]),
      ]),
      el("span", { class: "champ-picker-name", text: "None" }),
    ]);
    gridEl.appendChild(noneBtn);
  }

  const filtered = q ? agents.filter((a) => a.name.toLowerCase().includes(q)) : agents;

  if (filtered.length === 0 && gridEl.children.length === 0) {
    gridEl.appendChild(el("p", { class: "icon-picker-empty", text: "No agents found." }));
    return;
  }

  for (const agent of filtered) {
    const button = el("button", {
      type: "button",
      class: "champ-picker-item",
      title: agent.name,
      onClick: () => onPick(agent.name),
    }, [
      el("img", {
        src: agent.imgUrl,
        alt: agent.name,
        loading: "lazy",
        class: "champ-picker-img",
      }),
      el("span", { class: "champ-picker-name", text: agent.name }),
    ]);
    gridEl.appendChild(button);
  }
}

/**
 * Opens a searchable modal grid of VALORANT agents with live portrait icons.
 * Resolves with the agent name string (e.g. "Jett", "None"), or null if
 * cancelled. Mirrors champion-picker.js's shape for League.
 */
export function openAgentPicker({ title = "Select Agent", allowNone = true } = {}) {
  return new Promise((resolve) => {
    let resolved = false;

    function finish(agentName) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(agentName);
    }

    const overlay = openOverlay(() => {
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    });

    const box = el("div", { class: "modal-box champ-picker-box" });
    box.appendChild(el("h2", { text: title }));

    const search = el("input", {
      type: "text",
      class: "icon-picker-search",
      placeholder: "Type agent name...",
      autofocus: "true",
    });
    box.appendChild(search);

    const grid = el("div", { class: "champ-picker-grid" });
    grid.appendChild(el("p", { class: "icon-picker-empty", text: "Loading agents..." }));
    box.appendChild(grid);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    loadAgents()
      .then((agents) => {
        function update() {
          renderAgentGrid(grid, agents, finish, { allowNone, query: search.value });
        }

        update();
        search.oninput = update;

        search.onkeydown = (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            const firstItem = grid.querySelector(".champ-picker-item");
            if (firstItem) firstItem.click();
          }
        };
      })
      .catch((error) => {
        grid.innerHTML = "";
        grid.appendChild(
          el("p", { class: "icon-picker-empty", text: `Could not load agents: ${error.message}` })
        );
      });

    search.focus();
  });
}
