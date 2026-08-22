import { callAction, fetchFeatures, reportClientError } from "./api.js";
import { el } from "./components.js";
import { openOverlay, closeModal } from "./modal.js";

/**
 * Opens a checklist of game modes a feature should be restricted to.
 * Backed by `get_available_queues` (League: live from the LCU; Valorant: a
 * curated static list) and `toggle_mode`, both dispatched through the same
 * generic per-feature action mechanism every other picker uses.
 */
export function openModePicker({ featureKey, modalTitle = "Select Modes" } = {}) {
  return new Promise((resolve) => {
    let changed = false;

    function finish() {
      closeModal();
      resolve(changed);
    }

    const overlay = openOverlay(finish);

    const box = el("div", { class: "modal-box mode-picker-box" });
    box.appendChild(el("h2", { text: modalTitle }));
    box.appendChild(
      el("p", {
        class: "modal-description",
        text: "Leave everything unchecked to run in every mode. Check specific ones to restrict it to just those.",
      })
    );

    const list = el("div", { class: "mode-picker-list" });
    list.appendChild(el("p", { class: "icon-picker-empty", text: "Loading..." }));
    box.appendChild(list);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Done", onClick: finish }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    Promise.all([
      callAction(featureKey, "get_available_queues", {}).then((res) => res.result || []),
      fetchFeatures().then((features) => features[featureKey]?.modes || []),
    ])
      .then(([queues, selected]) => {
        const selectedSet = new Set(selected);
        list.innerHTML = "";

        if (queues.length === 0) {
          list.appendChild(el("p", { class: "icon-picker-empty", text: "No modes available." }));
          return;
        }

        for (const queue of queues) {
          const checkbox = el("input", { type: "checkbox" });
          checkbox.checked = selectedSet.has(queue.id);
          checkbox.onchange = async () => {
            checkbox.disabled = true;
            try {
              await callAction(featureKey, "toggle_mode", { queue_id: queue.id });
              changed = true;
            } catch (error) {
              checkbox.checked = !checkbox.checked;
              reportClientError(`Toggling mode failed: ${error.message}`, error.stack, "action");
            } finally {
              checkbox.disabled = false;
            }
          };
          list.appendChild(
            el("label", { class: "mode-picker-row" }, [checkbox, el("span", { text: queue.name })])
          );
        }
      })
      .catch((error) => {
        list.innerHTML = "";
        list.appendChild(el("p", { class: "icon-picker-empty", text: `Could not load modes: ${error.message}` }));
      });
  });
}
