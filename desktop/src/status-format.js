import { el } from "./components.js";

export const STATUS_FIELD_LABELS = {
  enabled: "Ativo",
  instalock_enabled: "Instalock",
  instalock_champion: "Campeão (instalock)",
  autoban_enabled: "AutoBan",
  autoban_champion: "Campeão (autoban)",
  queue_id: "Fila (ID)",
  queue_name: "Fila",
  first_position: "1ª posição",
  second_position: "2ª posição",
  provider: "Provedor",
  disconnected: "Chat desconectado",
};

const BOOLEAN_FIELD_PATTERN = /(^enabled$|_enabled$|^disconnected$)/;

export function isBooleanField(field, value) {
  return typeof value === "boolean" && BOOLEAN_FIELD_PATTERN.test(field);
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  return String(value);
}

/** Small colored pill for a boolean flag — green when the feature is actively on. */
export function statusPill(field, value) {
  if (field === "disconnected") {
    // "disconnected: true" means chat is OFF — invert so green means connected/live.
    return el("span", { class: `status-pill ${value ? "" : "on"}`, text: value ? "Desconectado" : "Conectado" });
  }
  return el("span", { class: `status-pill ${value ? "on" : ""}`, text: value ? "Ativo" : "Inativo" });
}
