import { el } from "./components.js";
import { getSkinList } from "./ddragon.js";
import { openOverlay, closeModal } from "./modal.js";

const PAGE_SIZE = 60;

function setupInfiniteSkinGrid(gridEl, onPick) {
  let renderedCount = 0;
  let currentList = [];

  function appendNextBatch() {
    if (renderedCount >= currentList.length) return;
    const nextBatch = currentList.slice(renderedCount, renderedCount + PAGE_SIZE);
    renderedCount += nextBatch.length;

    for (const skin of nextBatch) {
      const button = el(
        "button",
        {
          type: "button",
          class: "skin-picker-item",
          title: `${skin.champion} - ${skin.name} (ID: ${skin.id})`,
          onClick: () => onPick(skin.id),
        },
        [
          el("img", {
            src: skin.imgUrl,
            alt: skin.name,
            loading: "lazy",
            class: "skin-picker-img",
            onError: (e) => {
              e.target.style.display = "none";
            },
          }),
          el("div", { class: "skin-picker-info" }, [
            el("span", { class: "skin-picker-champ", text: skin.champion || "" }),
            el("span", { class: "skin-picker-name", text: skin.name }),
          ]),
        ]
      );
      gridEl.appendChild(button);
    }
  }

  function reset(filteredList) {
    gridEl.innerHTML = "";
    gridEl.scrollTop = 0;
    renderedCount = 0;
    currentList = filteredList;
    if (currentList.length === 0) {
      gridEl.appendChild(el("p", { class: "icon-picker-empty", text: "No skins found." }));
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
 * Opens a searchable modal grid of champion skins with live splash tiles
 * and smooth infinite scroll. Resolves with the skinId number, or null if cancelled.
 */
export function openSkinPicker({ title = "Choose Profile Background" } = {}) {
  return new Promise((resolve) => {
    let resolved = false;

    function finish(skinId) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(skinId);
    }

    const overlay = openOverlay(() => {
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    });

    const box = el("div", { class: "modal-box skin-picker-box" });
    box.appendChild(el("h2", { text: title }));

    const search = el("input", {
      type: "text",
      class: "icon-picker-search",
      placeholder: "Search by champion or skin name...",
      autofocus: "true",
    });
    box.appendChild(search);

    const grid = el("div", { class: "skin-picker-grid" });
    grid.appendChild(el("p", { class: "icon-picker-empty", text: "Loading skins..." }));
    box.appendChild(grid);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    getSkinList()
      .then((skins) => {
        const scroller = setupInfiniteSkinGrid(grid, finish);
        scroller.reset(skins);

        const debouncedSearch = debounce(() => {
          const q = search.value.trim().toLowerCase();
          const filtered = q
            ? skins.filter(
                (s) =>
                  s.name.toLowerCase().includes(q) ||
                  s.champion.toLowerCase().includes(q) ||
                  String(s.id).includes(q)
              )
            : skins;
          scroller.reset(filtered);
        }, 150);

        search.oninput = debouncedSearch;

        search.onkeydown = (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            const firstItem = grid.querySelector(".skin-picker-item");
            if (firstItem) firstItem.click();
          }
        };
      })
      .catch((error) => {
        grid.innerHTML = "";
        grid.appendChild(
          el("p", { class: "icon-picker-empty", text: `Could not load skins: ${error.message}` })
        );
      });

    search.focus();
  });
}
