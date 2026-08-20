const BADGE_MODE_OPTIONS = [
  { value: "empty", label: "Empty" },
  { value: "copy", label: "Copy Highest Badge" },
  { value: "glitched", label: "Glitched (Manual ID)" },
];

// Every feature with a persistent on/off state gets a switch here
export const FEATURE_TOGGLES = {
  auto_accept: [{ field: "enabled", label: "Enabled", action: null }],
  chat_toggle: [{ field: "disconnected", label: "Chat Connected", action: null, invert: true }],
  instalock_autoban: [
    { field: "instalock_enabled", label: "Instalock", action: "toggle_instalock" },
    { field: "autoban_enabled", label: "AutoBan", action: "toggle_auto_ban" },
  ],
};

// Declarative config: each feature key maps to a list of actions
export const FEATURE_ACTIONS = {
  instalock_autoban: [
    {
      label: "Set Instalock",
      action: "set_instalock_champion",
      kind: "champion-picker",
      pickerTitle: "Select Champion for Instalock",
      modalTitle: "Set Instalock",
      allowNone: true,
      paramName: "champion_name",
    },
    {
      label: "Set AutoBan",
      action: "set_auto_ban_champion",
      kind: "champion-picker",
      pickerTitle: "Select Champion for AutoBan",
      modalTitle: "Set AutoBan",
      allowNone: true,
      paramName: "champion_name",
    },
  ],
  profile_icon: [
    { label: "Choose", action: "change", kind: "icon-picker", iconKind: "profile", modalTitle: "Choose Profile Icon" },
  ],
  client_icon: [
    { label: "Choose", action: "change", kind: "icon-picker", iconKind: "client", modalTitle: "Choose Client Icon" },
  ],
  background: [
    { label: "Choose", action: "change", kind: "skin-picker", modalTitle: "Choose Background" },
  ],
  badges: [
    {
      label: "Change",
      action: "change",
      modalTitle: "Change Badges",
      fields: [
        { name: "mode", label: "Mode", type: "select", options: BADGE_MODE_OPTIONS },
        { name: "glitched_id", label: "Glitched ID (0-5, if applicable)", type: "number" },
      ],
    },
  ],
  status_message: [
    { label: "Change", action: "change", modalTitle: "Change Status Message", fields: [{ name: "status", label: "Message" }] },
  ],
  remove_friends: [
    { label: "Remove", action: "remove_all", modalTitle: "Remove All Friends", fields: [], confirmOnly: true },
  ],
  restart_ux: [
    { label: "Restart", action: "restart", modalTitle: "Restart Client UX", fields: [], confirmOnly: true },
  ],
  dodge: [{ label: "Dodge", action: "dodge", modalTitle: "Dodge Queue", fields: [], confirmOnly: true }],
};
