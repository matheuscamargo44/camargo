const AVAILABILITY_OPTIONS = [
  { value: "mobile", label: "Mobile (League+ Icon)" },
  { value: "chat", label: "Online" },
  { value: "away", label: "Away" },
  { value: "dnd", label: "Do Not Disturb" },
  { value: "offline", label: "Offline (Appear Offline)" },
];

const RANKED_TIER_OPTIONS = [
  { value: "CHALLENGER", label: "Challenger" },
  { value: "GRANDMASTER", label: "Grandmaster" },
  { value: "MASTER", label: "Master" },
  { value: "DIAMOND", label: "Diamond" },
  { value: "EMERALD", label: "Emerald" },
  { value: "PLATINUM", label: "Platinum" },
  { value: "GOLD", label: "Gold" },
  { value: "SILVER", label: "Silver" },
  { value: "BRONZE", label: "Bronze" },
  { value: "IRON", label: "Iron" },
  { value: "UNRANKED", label: "Unranked" },
];

const RANKED_DIVISION_OPTIONS = [
  { value: "I", label: "Division I" },
  { value: "II", label: "Division II" },
  { value: "III", label: "Division III" },
  { value: "IV", label: "Division IV" },
];

// Every feature with a persistent on/off state gets a switch here
export const FEATURE_TOGGLES = {
  auto_accept: [{ field: "enabled", label: "Enabled", action: null }],
  auto_play_again: [{ field: "enabled", label: "Enabled", action: null }],
  auto_honor: [{ field: "enabled", label: "Enabled", action: null }],
  auto_party_invite: [{ field: "enabled", label: "Auto Invite", action: null }],
  aram_bench_swap: [{ field: "enabled", label: "Enabled", action: null }],
  random_skin: [{ field: "enabled", label: "Enabled", action: null }],
  chat_toggle: [{ field: "disconnected", label: "Chat Connected", action: null, invert: true }],
  instalock: [{ field: "enabled", label: "Enabled", action: null }],
  autoban: [{ field: "enabled", label: "Enabled", action: null }],
};

// Declarative config: each feature key maps to a list of actions
export const FEATURE_ACTIONS = {
  instalock: [
    {
      label: "Set Champion",
      action: "set_champion",
      kind: "champion-picker",
      pickerTitle: "Select Champion for Instalock",
      modalTitle: "Set Instalock Champion",
      allowNone: true,
      paramName: "champion_name",
    },
  ],
  autoban: [
    {
      label: "Set Champion",
      action: "set_champion",
      kind: "champion-picker",
      pickerTitle: "Select Champion for AutoBan",
      modalTitle: "Set AutoBan Champion",
      allowNone: true,
      paramName: "champion_name",
    },
  ],
  aram_bench_swap: [
    {
      label: "Set Target",
      action: "set_champion",
      kind: "champion-picker",
      pickerTitle: "Select Target ARAM Champion",
      modalTitle: "Set ARAM Target Champion",
      allowNone: true,
      paramName: "champion_name",
    },
  ],
  auto_party_invite: [
    {
      label: "Edit Group",
      action: "set_summoners",
      modalTitle: "Set Auto Party Invite List",
      fields: [{ name: "summoners", label: "Summoner Names (separated by comma)", placeholder: "Player1#BR1, Player2#BR1" }],
    },
    {
      label: "Invite Now",
      action: "invite_now",
      modalTitle: "Invite Friends Now",
      confirmOnly: true,
    },
  ],
  practice_tool: [
    {
      label: "Create 5v5 Lobby",
      action: "create_lobby",
      modalTitle: "Create 5v5 Practice Tool Lobby with Bots",
      confirmOnly: true,
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
    { label: "Change", action: "change", kind: "badge-picker", modalTitle: "Change Badges" },
  ],
  challenge_titles: [
    {
      label: "Choose",
      action: "set_title",
      kind: "title-picker",
      modalTitle: "Choose Challenge Title",
    },
  ],
  mass_disenchant: [
    {
      label: "Forge Keys",
      action: "forge_keys",
      modalTitle: "Forge Key Fragments",
      confirmOnly: true,
    },
    {
      label: "Open Chests",
      action: "open_chests",
      modalTitle: "Open All Available Chests & Capsules",
      confirmOnly: true,
    },
    {
      label: "Disenchant (BE)",
      action: "disenchant_champions",
      modalTitle: "Disenchant All Champion Shards for Blue Essence",
      confirmOnly: true,
    },
    {
      label: "Disenchant (All)",
      action: "disenchant_all",
      modalTitle: "Disenchant All Shards (Champions, Wards, Statstones)",
      confirmOnly: true,
    },
  ],
  status_message: [
    { label: "Change", action: "change", modalTitle: "Change Status Message", fields: [{ name: "status", label: "Message" }] },
  ],
  presence_status: [
    {
      label: "Change",
      action: "set_presence",
      modalTitle: "Change Presence Status",
      fields: [{ name: "availability", label: "Availability", type: "select", options: AVAILABILITY_OPTIONS }],
    },
  ],
  ranked_presence: [
    {
      label: "Set Rank",
      action: "set_tier",
      modalTitle: "Set Ranked Chat Presence",
      fields: [
        { name: "tier", label: "Tier", type: "select", options: RANKED_TIER_OPTIONS },
        { name: "division", label: "Division", type: "select", options: RANKED_DIVISION_OPTIONS },
      ],
    },
  ],
  friend_requests: [
    {
      label: "Accept All",
      action: "accept_all",
      modalTitle: "Accept All Friend Requests",
      confirmOnly: true,
    },
    {
      label: "Reject All",
      action: "reject_all",
      modalTitle: "Reject All Friend Requests",
      confirmOnly: true,
      variant: "danger",
    },
  ],
  remove_friends: [
    { label: "Remove", action: "remove_all", modalTitle: "Remove All Friends", fields: [], confirmOnly: true, variant: "danger" },
  ],
  restart_ux: [
    { label: "Restart", action: "restart", modalTitle: "Restart Client UX", fields: [], confirmOnly: true },
  ],
  dodge: [{ label: "Dodge", action: "dodge", modalTitle: "Dodge Queue", fields: [], confirmOnly: true, variant: "danger" }],
};
