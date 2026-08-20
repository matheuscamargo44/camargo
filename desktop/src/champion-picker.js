import { el } from "./components.js";
import { getLatestVersion } from "./ddragon.js";
import { openOverlay, closeModal } from "./modal.js";

const championsUrlFor = (version) =>
  `https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/champion.json`;
const championImgUrlFor = (version, fullImg) =>
  `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${fullImg}`;

let cachedChampions = null; // [{ id, name, key, imgUrl }]

async function loadChampions() {
  if (cachedChampions) return cachedChampions;

  const version = await getLatestVersion();
  const data = await fetch(championsUrlFor(version)).then((r) => r.json());

  cachedChampions = Object.values(data.data)
    .map((champ) => ({
      id: champ.id,
      name: champ.name,
      key: champ.key,
      imgUrl: championImgUrlFor(version, champ.image.full),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));

  return cachedChampions;
}

function renderChampionGrid(gridEl, champions, onPick, { allowNone = true, query = "" }) {
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
        // Slash / Ban SVG icon
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

  const filtered = q
    ? champions.filter((c) => c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q))
    : champions;

  if (filtered.length === 0 && gridEl.children.length === 0) {
    gridEl.appendChild(el("p", { class: "icon-picker-empty", text: "No champions found." }));
    return;
  }

  for (const champ of filtered) {
    const button = el("button", {
      type: "button",
      class: "champ-picker-item",
      title: champ.name,
      onClick: () => onPick(champ.name),
    }, [
      el("img", {
        src: champ.imgUrl,
        alt: champ.name,
        loading: "lazy",
        class: "champ-picker-img",
      }),
      el("span", { class: "champ-picker-name", text: champ.name }),
    ]);
    gridEl.appendChild(button);
  }
}

/**
 * Opens a searchable modal grid of champions with live portrait icons.
 * Resolves with the champion name string (e.g. "Ahri", "None"),
 * or null if cancelled.
 */
export function openChampionPicker({
  title = "Select Champion",
  allowNone = true,
} = {}) {
  return new Promise((resolve) => {
    let resolved = false;

    function finish(champName) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(champName);
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
      placeholder: "Type champion name...",
      autofocus: "true",
    });
    box.appendChild(search);

    const grid = el("div", { class: "champ-picker-grid" });
    grid.appendChild(el("p", { class: "icon-picker-empty", text: "Loading champions..." }));
    box.appendChild(grid);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    loadChampions()
      .then((champions) => {
        function update() {
          renderChampionGrid(grid, champions, finish, {
            allowNone,
            query: search.value,
          });
        }

        update();
        search.oninput = update;

        // Press Enter to pick the first displayed champion
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
          el("p", { class: "icon-picker-empty", text: `Could not load champions: ${error.message}` })
        );
      });

    search.focus();
  });
}
