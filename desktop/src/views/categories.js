// Maps backend Feature.category values (features/*.py) to the screens shown
// in the sidebar. "Game Tools" lives inside the Automação screen as a
// subsection, and "Settings" inside the Social screen, so the nav stays
// short instead of having a screen with a single card.
export const NAV_ITEMS = [
  { route: "/dashboard", label: "Painel" },
  { route: "/automation", label: "Automação" },
  { route: "/customization", label: "Customização" },
  { route: "/social", label: "Social & config" },
];

export const CATEGORY_LABELS = {
  Automation: "Automação",
  "Game Tools": "Ferramentas de Jogo",
  Customization: "Customização",
  Social: "Social",
  Settings: "Configurações",
};

export const AUTOMATION_SCREEN_CATEGORIES = ["Automation", "Game Tools"];
export const CUSTOMIZATION_SCREEN_CATEGORIES = ["Customization"];
export const SOCIAL_SCREEN_CATEGORIES = ["Social", "Settings"];
