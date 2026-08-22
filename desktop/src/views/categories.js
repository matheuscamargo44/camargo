// Top-level tabs. League of Legends groups three sub-tabs under one nav
// entry (see LEAGUE_SUB_TABS); Valorant and Logs are flat.
export const NAV_ITEMS = [
  { route: "/league/automation", matchPrefix: "/league", label: "League of Legends" },
  { route: "/valorant", label: "Valorant" },
  { route: "/logs", label: "Logs" },
];

// Sub-navigation shown inside the League of Legends tab.
export const LEAGUE_SUB_TABS = [
  { category: "Automation", route: "/league/automation", label: "Automation" },
  { category: "Customization", route: "/league/customization", label: "Customization" },
  { category: "Social", route: "/league/social", label: "Social" },
];

export const VALORANT_SCREEN_CATEGORIES = ["Valorant"];
