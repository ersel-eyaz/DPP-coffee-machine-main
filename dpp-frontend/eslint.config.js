// eslint.config.js (Flat Config + FlatCompat bridge)

import path from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";
import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import globals from "globals";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Bridge to load legacy ".eslintrc"-style shareable configs
const compat = new FlatCompat({
  baseDirectory: __dirname,
});

export default [
  // Ignore folders
  { ignores: ["node_modules", "dist", "build", "coverage"] },

  // Base JS recommended (already flat)
  js.configs.recommended,

  // Convert legacy shareable configs to flat on the fly
  // - React recommended rules
  // - React JSX runtime tweaks
  // - Turn off ESLint rules that conflict with Prettier
  ...compat.extends("plugin:react/recommended", "plugin:react/jsx-runtime", "prettier"),

  // Project rules/plugins
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "simple-import-sort": simpleImportSort,
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      // React hooks best practices
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // Vite Fast Refresh guard
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],

      // Keep imports tidy (Ruff-like import sorting)
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
    },
  },
];
