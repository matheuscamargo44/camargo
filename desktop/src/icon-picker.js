import { el } from "./components.js";

const VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json";
const iconsUrlFor = (version) =>
  `https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/profileicon.json`;
const iconImageUrlFor = (version, id) =>
  `https://ddragon.leagueoflegends.com/cdn/${version}/img/profileicon/${id}.png`;

let cachedIcons = null; // [{ id, url }]
let overlayEl = null;

function ensureOverlay() {
  if (overlayEl) return overlayEl;
  overlayEl = document.createElement("div");
  overlayEl.className = "modal-overlay";
  overlayEl.hidden = true;
  document.body.appendChild(overlayEl);
  return overlayEl;
}

async function loadIcons() {
  if (cachedIcons) return cachedIcons;

  const versions = await fetch(VERSIONS_URL).then((r) => r.json());
  const latest = versions[0];
  const data = await fetch(iconsUrlFor(latest)).then((r) => r.json());

  cachedIcons = Object.keys(data.data)
    .map(Number)
    .sort((a, b) => a - b)
    .map((id) => ({ id, url: iconImageUrlFor(latest, id) }));

  return cachedIcons;
}

const MAX_RENDERED_ICONS = 240;

function renderGrid(gridEl, icons, onPick) {
  gridEl.innerHTML = "";
  if (icons.length === 0) {
    gridEl.appendChild(el("p", { class: "icon-picker-empty", text: "Nenhum ícone encontrado." }));
    return;
  }
  const visible = icons.slice(0, MAX_RENDERED_ICONS);
  for (const icon of visible) {
    const button = el("button", { type: "button", class: "icon-picker-item", title: String(icon.id) });
    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = icon.url;
    img.alt = `Ícone ${icon.id}`;
    button.appendChild(img);
    button.onclick = () => onPick(icon.id);
    gridEl.appendChild(button);
  }
  if (icons.length > visible.length) {
    gridEl.appendChild(
      el("p", {
        class: "icon-picker-empty",
        text: `Mostrando ${visible.length} de ${icons.length} — refine a busca para ver mais.`,
      })
    );
  }
}

/**
 * Opens a searchable grid of League profile icons pulled live from
 * Data Dragon. Resolves with the chosen icon id, or null if cancelled.
 */
export function openIconPicker({ kind = "profile" } = {}) {
  return new Promise((resolve) => {
    const overlay = ensureOverlay();
    overlay.innerHTML = "";
    overlay.hidden = false;
    overlay.onclick = (event) => {
      if (event.target === overlay) finish(null);
    };

    const box = el("div", { class: "modal-box icon-picker-box" });
    box.appendChild(
      el("h2", { text: kind === "client" ? "Escolher ícone do client" : "Escolher ícone de perfil" })
    );

    const search = el("input", {
      type: "text",
      class: "icon-picker-search",
      placeholder: "Buscar por ID...",
    });
    box.appendChild(search);

    const grid = el("div", { class: "icon-picker-grid" });
    grid.appendChild(el("p", { class: "icon-picker-empty", text: "Carregando ícones..." }));
    box.appendChild(grid);

    const actions = el("div", { class: "modal-actions" }, [
      el("button", { type: "button", text: "Cancelar", onClick: () => finish(null) }),
    ]);
    box.appendChild(actions);

    overlay.appendChild(box);

    function finish(iconId) {
      overlay.hidden = true;
      overlay.innerHTML = "";
      resolve(iconId);
    }

    loadIcons()
      .then((icons) => {
        renderGrid(grid, icons, finish);
        search.oninput = () => {
          const query = search.value.trim();
          const filtered = query ? icons.filter((icon) => String(icon.id).includes(query)) : icons;
          renderGrid(grid, filtered, finish);
        };
      })
      .catch((error) => {
        grid.innerHTML = "";
        grid.appendChild(
          el("p", { class: "icon-picker-empty", text: `Não foi possível carregar os ícones: ${error.message}` })
        );
      });

    search.focus();
  });
}
