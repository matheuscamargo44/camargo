import { el } from "./components.js";
import { getLatestVersion, profileIconUrl } from "./ddragon.js";
import { openOverlay, closeModal } from "./modal.js";

const iconsUrlFor = (version) =>
  `https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/profileicon.json`;

let cachedIcons = null; // [{ id, url }]

async function loadIcons() {
  if (cachedIcons) return cachedIcons;

  const version = await getLatestVersion();
  const data = await fetch(iconsUrlFor(version)).then((r) => r.json());

  cachedIcons = Object.keys(data.data)
    .map(Number)
    .sort((a, b) => a - b)
    .map((id) => ({ id, url: profileIconUrl(id, version) }));

  return cachedIcons;
}

const PAGE_SIZE = 80;

function setupInfiniteGrid(gridEl, onPick) {
  let renderedCount = 0;
  let currentList = [];

  function appendNextBatch() {
    if (renderedCount >= currentList.length) return;
    const nextBatch = currentList.slice(renderedCount, renderedCount + PAGE_SIZE);
    renderedCount += nextBatch.length;

    for (const icon of nextBatch) {
      const button = el("button", {
        type: "button",
        class: "icon-picker-item",
        title: String(icon.id),
      });
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = icon.url;
      img.alt = `Icon ${icon.id}`;
      button.appendChild(img);
      button.onclick = () => onPick(icon.id);
      gridEl.appendChild(button);
    }
  }

  function reset(filteredList) {
    gridEl.innerHTML = "";
    gridEl.scrollTop = 0;
    renderedCount = 0;
    currentList = filteredList;
    if (currentList.length === 0) {
      gridEl.appendChild(el("p", { class: "icon-picker-empty", text: "No icons found." }));
      return;
    }
    appendNextBatch();
  }

  gridEl.onscroll = () => {
    if (gridEl.scrollTop + gridEl.clientHeight >= gridEl.scrollHeight - 160) {
      appendNextBatch();
    }
  };

  return { reset };
}

/** Simple debounce helper */
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/**
 * Opens a searchable grid of League profile icons pulled live from
 * Data Dragon with smooth infinite scroll. Resolves with the chosen icon id,
 * or null if cancelled.
 */
export function openIconPicker({ kind = "profile" } = {}) {
  return new Promise((resolve) => {
    let resolved = false;

    function finish(iconId) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(iconId);
    }

    const overlay = openOverlay(() => {
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    });

    const box = el("div", { class: "modal-box icon-picker-box" });
    box.appendChild(
      el("h2", { text: kind === "client" ? "Choose Client Icon" : "Choose Profile Icon" })
    );

    const search = el("input", {
      type: "text",
      class: "icon-picker-search",
      placeholder: "Search by ID...",
    });
    box.appendChild(search);

    const grid = el("div", { class: "icon-picker-grid" });
    grid.appendChild(el("p", { class: "icon-picker-empty", text: "Loading icons..." }));
    box.appendChild(grid);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    loadIcons()
      .then((icons) => {
        const scroller = setupInfiniteGrid(grid, finish);
        scroller.reset(icons);

        const debouncedSearch = debounce(() => {
          const query = search.value.trim();
          const filtered = query ? icons.filter((icon) => String(icon.id).includes(query)) : icons;
          scroller.reset(filtered);
        }, 150);

        search.oninput = debouncedSearch;
      })
      .catch((error) => {
        grid.innerHTML = "";
        grid.appendChild(
          el("p", { class: "icon-picker-empty", text: `Could not load icons: ${error.message}` })
        );
      });

    search.focus();
  });
}
