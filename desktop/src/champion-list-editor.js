import { callAction, fetchFeatures, reportClientError } from "./api.js";
import { championSquareUrl } from "./ddragon.js";
import { openChampionPicker } from "./champion-picker.js";
import { el } from "./components.js";
import { openOverlay, closeModal } from "./modal.js";

/**
 * Opens a modal to manage a feature's champion priority list: add via the
 * usual champion picker, remove with one click. Order is priority order —
 * the backend tries the first entry first and falls through the rest if
 * it's taken by a teammate or banned.
 */
export function openChampionListEditor({
  featureKey,
  statusField,
  addAction = "add_champion",
  removeAction = "remove_champion",
  modalTitle = "Champion Priority List",
} = {}) {
  return new Promise((resolve) => {
    let changed = false;
    let champions = [];

    function finish() {
      closeModal();
      resolve(changed);
    }

    const overlay = openOverlay(finish);

    const box = el("div", { class: "modal-box champ-list-editor-box" });
    box.appendChild(el("h2", { text: modalTitle }));
    box.appendChild(
      el("p", {
        class: "modal-description",
        text: "Tried in order — if the top pick is taken by a teammate or banned, the next one is used instead.",
      })
    );

    const list = el("div", { class: "champ-list-editor-rows" });
    list.appendChild(el("p", { class: "icon-picker-empty", text: "Loading..." }));
    box.appendChild(list);

    const addButton = el("button", { type: "button", class: "btn btn-secondary champ-list-add-btn", text: "+ Add Champion" });
    box.appendChild(addButton);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Done", onClick: finish }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    function render() {
      list.innerHTML = "";
      if (champions.length === 0) {
        list.appendChild(el("p", { class: "icon-picker-empty", text: "No champions set." }));
        return;
      }
      champions.forEach((name, index) => {
        const img = el("img", { src: championSquareUrl(name), class: "champ-list-row-img", alt: name });
        img.onerror = () => { img.style.display = "none"; };

        const row = el("div", { class: "champ-list-editor-row" }, [
          el("span", { class: "champ-list-row-priority", text: String(index + 1) }),
          img,
          el("span", { class: "champ-list-row-name", text: name }),
          el("button", {
            type: "button",
            class: "champ-list-row-remove",
            "aria-label": `Remove ${name}`,
            text: "×",
            onClick: async () => {
              try {
                await callAction(featureKey, removeAction, { champion_name: name });
                champions = champions.filter((c) => c !== name);
                changed = true;
                render();
              } catch (error) {
                reportClientError(`Removing ${name} failed: ${error.message}`, error.stack, "action");
              }
            },
          }),
        ]);
        list.appendChild(row);
      });
    }

    fetchFeatures()
      .then((features) => {
        champions = features[featureKey]?.[statusField] || [];
        render();
      })
      .catch((error) => {
        list.innerHTML = "";
        list.appendChild(el("p", { class: "icon-picker-empty", text: `Could not load: ${error.message}` }));
      });

    addButton.onclick = async () => {
      const name = await openChampionPicker({ title: "Add Champion", allowNone: false });
      if (name === null || champions.includes(name)) return;
      try {
        await callAction(featureKey, addAction, { champion_name: name });
        champions = [...champions, name];
        changed = true;
        render();
      } catch (error) {
        reportClientError(`Adding ${name} failed: ${error.message}`, error.stack, "action");
      }
    };
  });
}
