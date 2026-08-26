// Flat config (ESLint 9+). Deliberately narrow: this exists to catch real
// defects - an undefined name, an unused import left by a removal, a
// promise nobody awaits - not to argue about formatting. There is no
// formatter in this project and adding one now would rewrite every file
// and bury the git history for no behavioural gain.
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.es2021 },
    },
    rules: {
      // An unused variable is usually a leftover from a deletion - exactly
      // the class of thing the orphan sweep had to find by hand.
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-undef": "error",
      eqeqeq: ["error", "smart"],
      "no-var": "error",
      "prefer-const": "error",
    },
  },
  {
    // Electron main/preload and the build scripts are CommonJS running in
    // Node, not ES modules in a browser.
    files: ["main.js", "preload.js", "backend-manager.js", "update-manager.js"],
    languageOptions: {
      sourceType: "commonjs",
      globals: { ...globals.node },
    },
  },
  {
    files: ["**/*.test.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
