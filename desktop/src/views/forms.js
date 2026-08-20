const QUEUE_OPTIONS = [
  { value: "400", label: "Normal Draft Pick" },
  { value: "420", label: "Ranked Solo/Duo" },
  { value: "440", label: "Ranked Flex" },
  { value: "450", label: "ARAM" },
  { value: "480", label: "Swiftplay" },
  { value: "490", label: "Quickplay" },
  { value: "1090", label: "TFT Normal" },
  { value: "1100", label: "TFT Ranked" },
  { value: "1130", label: "TFT Hyper Roll" },
  { value: "1160", label: "TFT Double Up" },
];

const POSITION_OPTIONS = [
  { value: "", label: "(nenhuma)" },
  { value: "TOP", label: "Top" },
  { value: "JUNGLE", label: "Jungle" },
  { value: "MIDDLE", label: "Mid" },
  { value: "BOTTOM", label: "Bottom" },
  { value: "UTILITY", label: "Support" },
  { value: "FILL", label: "Fill" },
];

const BADGE_MODE_OPTIONS = [
  { value: "empty", label: "Vazio" },
  { value: "copy", label: "Copiar melhor badge" },
  { value: "glitched", label: "Glitched (ID manual)" },
];

// Every feature with a persistent on/off state gets a switch here — one
// entry per switch, so a card can have zero, one (auto_accept) or several
// (instalock_autoban). `action: null` means "use the generic
// POST /features/{key}/toggle endpoint"; otherwise it calls that named
// action via POST /features/{key}/actions/{action}. `invert` flips the
// switch's on/off reading relative to the raw status field (used for
// chat_toggle, where `disconnected: true` means the switch is OFF).
export const FEATURE_TOGGLES = {
  auto_accept: [{ field: "enabled", label: "Ligado", action: null }],
  ragequeue: [{ field: "enabled", label: "Ligado", action: null }],
  chat_toggle: [{ field: "disconnected", label: "Chat conectado", action: null, invert: true }],
  instalock_autoban: [
    { field: "instalock_enabled", label: "Instalock", action: "toggle_instalock" },
    { field: "autoban_enabled", label: "AutoBan", action: "toggle_auto_ban" },
  ],
};

// Declarative config: each feature key maps to a list of actions it exposes
// through POST /features/{key}/actions/{action}. `confirmOnly` skips the
// field form and just asks for confirmation before calling the action.
export const FEATURE_ACTIONS = {
  instalock_autoban: [
    {
      label: "Definir Instalock",
      action: "set_instalock_champion",
      fields: [{ name: "champion_name", label: "Campeão (ou 'Random')", placeholder: "Random" }],
    },
    {
      label: "Definir AutoBan",
      action: "set_auto_ban_champion",
      fields: [{ name: "champion_name", label: "Campeão" }],
    },
  ],
  ragequeue: [
    {
      label: "Configurar fila",
      action: "configure",
      fields: [
        { name: "queue_id", label: "Fila", type: "select", options: QUEUE_OPTIONS },
        { name: "first_position", label: "1ª posição", type: "select", options: POSITION_OPTIONS },
        { name: "second_position", label: "2ª posição", type: "select", options: POSITION_OPTIONS },
      ],
    },
  ],
  profile_icon: [
    { label: "Escolher ícone de perfil", action: "change", kind: "icon-picker", iconKind: "profile" },
  ],
  client_icon: [
    { label: "Escolher ícone do client", action: "change", kind: "icon-picker", iconKind: "client" },
  ],
  background: [
    {
      label: "Trocar background",
      action: "change",
      fields: [{ name: "skin_id", label: "ID da skin (veja em communitydragon.org)", type: "number" }],
    },
  ],
  badges: [
    {
      label: "Atualizar badges",
      action: "change",
      fields: [
        { name: "mode", label: "Modo", type: "select", options: BADGE_MODE_OPTIONS },
        { name: "glitched_id", label: "Glitched ID (0-5, se aplicável)", type: "number" },
      ],
    },
  ],
  riot_id: [
    {
      label: "Trocar Riot ID",
      action: "change",
      fields: [
        { name: "name", label: "Nome" },
        { name: "tag", label: "Tag" },
      ],
    },
  ],
  status_message: [
    { label: "Trocar mensagem de status", action: "change", fields: [{ name: "status", label: "Mensagem" }] },
  ],
  remove_friends: [
    { label: "Remover todos os amigos", action: "remove_all", fields: [], confirmOnly: true },
  ],
  restart_ux: [
    { label: "Reiniciar client (UX)", action: "restart", fields: [], confirmOnly: true },
  ],
  dodge: [{ label: "Dar dodge no champ select", action: "dodge", fields: [], confirmOnly: true }],
};
