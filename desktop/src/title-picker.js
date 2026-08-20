import { callAction } from "./api.js";
import { el } from "./components.js";
import { openOverlay, closeModal } from "./modal.js";

/**
 * Opens a visual Title Picker modal showing the user's unlocked titles.
 * Resolves with `{ title_id }` or `null` if cancelled.
 */
export function openTitlePicker({ title = "Choose Challenge Title" } = {}) {
  return new Promise(async (resolve) => {
    let resolved = false;

    function finish(result) {
      if (resolved) return;
      resolved = true;
      closeModal();
      resolve(result);
    }

    const overlay = openOverlay(() => {
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    });

    const box = el("div", { class: "modal-box title-picker-box" });
    box.appendChild(el("h2", { text: title }));
    box.appendChild(
      el("p", {
        class: "modal-description",
        text: "Select an unlocked title from your account to display on your profile.",
      })
    );

    const searchInput = el("input", {
      type: "text",
      class: "picker-search",
      placeholder: "Search titles...",
    });
    box.appendChild(searchInput);

    const listContainer = el("div", { class: "title-picker-list" });
    listContainer.appendChild(el("div", { class: "picker-loading", text: "Loading unlocked titles..." }));
    box.appendChild(listContainer);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);
    searchInput.focus();

    // Fetch titles from backend
    let allTitles = [];
    try {
      const res = await callAction("challenge_titles", "get_titles", {});
      allTitles = res.result || [];
    } catch {
      allTitles = [];
    }

    function renderList(query = "") {
      listContainer.innerHTML = "";
      const q = query.toLowerCase().trim();

      // Top preset: Clear / None
      const clearBtn = el(
        "button",
        {
          type: "button",
          class: "title-picker-item clear-item",
          onClick: () => finish({ title_id: "" }),
        },
        [
          el("div", { class: "title-picker-info" }, [
            el("span", { class: "title-picker-name", text: "None / Clear Title" }),
            el("span", { class: "title-picker-desc", text: "Remove the title from your profile" }),
          ]),
        ]
      );
      listContainer.appendChild(clearBtn);

      const filtered = allTitles.filter(
        (t) => t.name.toLowerCase().includes(q) || (t.desc && t.desc.toLowerCase().includes(q))
      );

      if (filtered.length === 0 && q) {
        listContainer.appendChild(
          el("div", { class: "picker-empty", text: "No matching unlocked titles found." })
        );
        return;
      }

      for (const item of filtered) {
        const btn = el(
          "button",
          {
            type: "button",
            class: "title-picker-item",
            onClick: () => finish({ title_id: item.id }),
          },
          [
            el("div", { class: "title-picker-info" }, [
              el("span", { class: "title-picker-name", text: item.name }),
              item.desc ? el("span", { class: "title-picker-desc", text: item.desc }) : null,
            ]),
          ]
        );
        listContainer.appendChild(btn);
      }
    }

    renderList();

    searchInput.addEventListener("input", () => {
      renderList(searchInput.value);
    });
  });
}
