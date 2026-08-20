import { el } from "./components.js";
import { openOverlay, closeModal } from "./modal.js";

const GLITCHED_CATEGORIES = [
  {
    id: 0,
    name: "Crystal",
    desc: "Total Points Crystal",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12l4 6-10 12L2 9z"/></svg>`,
    color: "#4ee2ff",
  },
  {
    id: 1,
    name: "Imagination",
    desc: "Creative Play",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`,
    color: "#ff84ff",
  },
  {
    id: 2,
    name: "Expertise",
    desc: "Mastery & Skill",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 14.14 14.14"/><circle cx="12" cy="12" r="4"/></svg>`,
    color: "#ff5e5e",
  },
  {
    id: 3,
    name: "Veterancy",
    desc: "Match Experience",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    color: "#ffa733",
  },
  {
    id: 4,
    name: "Teamwork",
    desc: "Synergy & Assists",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
    color: "#44e08c",
  },
  {
    id: 5,
    name: "Collection",
    desc: "Skins & Cosmetics",
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 4h20v16H2z"/><path d="M2 10h20"/><path d="M12 4v16"/></svg>`,
    color: "#f5d13b",
  },
];

/**
 * Opens a visual badge selector modal.
 * Resolves with `{ mode, glitched_id }` or `null` if cancelled.
 */
export function openBadgePicker({ title = "Change Profile Badges" } = {}) {
  return new Promise((resolve) => {
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

    const box = el("div", { class: "modal-box badge-picker-box" });
    box.appendChild(el("h2", { text: title }));
    box.appendChild(
      el("p", {
        class: "modal-description",
        text: "Choose an arrangement or special category token for your profile.",
      })
    );

    const content = el("div", { class: "badge-picker-content" });

    // ── Quick Presets (Empty & Copy) ──────────────────────────────
    const presetsRow = el("div", { class: "badge-picker-presets" });

    // Empty Slot Card
    const emptyBtn = el(
      "button",
      {
        type: "button",
        class: "badge-preset-card",
        onClick: () => finish({ mode: "empty" }),
      },
      [
        el("div", { class: "badge-slot-preview empty" }, [
          el("div", { class: "badge-slot-circle dashed" }),
          el("div", { class: "badge-slot-circle dashed" }),
          el("div", { class: "badge-slot-circle dashed" }),
        ]),
        el("div", { class: "badge-preset-text" }, [
          el("span", { class: "badge-preset-title", text: "Empty Profile" }),
          el("span", { class: "badge-preset-desc", text: "Clear all 3 badge slots" }),
        ]),
      ]
    );
    presetsRow.appendChild(emptyBtn);

    // Clone Highest Badge Card
    const copyBtn = el(
      "button",
      {
        type: "button",
        class: "badge-preset-card",
        onClick: () => finish({ mode: "copy" }),
      },
      [
        el("div", { class: "badge-slot-preview copy" }, [
          el("div", { class: "badge-slot-circle solid" }),
          el("div", { class: "badge-slot-circle solid" }),
          el("div", { class: "badge-slot-circle solid" }),
        ]),
        el("div", { class: "badge-preset-text" }, [
          el("span", { class: "badge-preset-title", text: "Triple Top Badge" }),
          el("span", { class: "badge-preset-desc", text: "Clone highest badge x3" }),
        ]),
      ]
    );
    presetsRow.appendChild(copyBtn);

    content.appendChild(presetsRow);

    // ── Glitched / Special Tokens Section ─────────────────────────
    const glitchedHeader = el("div", { class: "badge-section-header" }, [
      el("span", { text: "Special Category Tokens (3x Glitched)" }),
    ]);
    content.appendChild(glitchedHeader);

    const glitchedGrid = el("div", { class: "badge-glitched-grid" });

    for (const cat of GLITCHED_CATEGORIES) {
      const btn = el(
        "button",
        {
          type: "button",
          class: "badge-glitched-card",
          title: `${cat.name} (ID ${cat.id})`,
          onClick: () => finish({ mode: "glitched", glitched_id: cat.id }),
        },
        [
          el("div", {
            class: "badge-glitched-icon",
            html: cat.icon,
            style: `color: ${cat.color}; background: ${cat.color}15; border-color: ${cat.color}35`,
          }),
          el("div", { class: "badge-glitched-info" }, [
            el("span", { class: "badge-glitched-name", text: cat.name }),
            el("span", { class: "badge-glitched-desc", text: cat.desc }),
          ]),
        ]
      );
      glitchedGrid.appendChild(btn);
    }

    content.appendChild(glitchedGrid);
    box.appendChild(content);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancel", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);
  });
}
