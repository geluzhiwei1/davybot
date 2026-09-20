/**
 * Theme store — Zustand store for theme state management.
 * Migrated from legalbot/webui/src/stores/themeStore.ts
 */
import { create } from "zustand";
import type { ThemeMode } from "./theme/types";
import { darkTheme, lightTheme, applyTheme, getSystemTheme } from "./theme";

const STORAGE_KEY = "legent-theme-mode";

interface ThemeState {
  mode: ThemeMode;
  activeThemeId: string;
  switchCount: number;
  lastSwitchedAt: string | null;

  // Actions
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
  getEffectiveThemeId: () => string;
}

function resolveThemeId(mode: ThemeMode): string {
  if (mode === "system") return getSystemTheme();
  return mode;
}

function saveMode(mode: ThemeMode): void {
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore
  }
}

function loadMode(): ThemeMode {
  try {
    if (typeof localStorage === "undefined") return "dark";
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light" || stored === "system") return stored;
  } catch {
    // ignore
  }
  return "dark";
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const initialMode = loadMode();
  const initialThemeId = resolveThemeId(initialMode);

  // Apply on init
  const theme = initialThemeId === "dark" ? darkTheme : lightTheme;
  applyTheme(theme);

  return {
    mode: initialMode,
    activeThemeId: initialThemeId,
    switchCount: 0,
    lastSwitchedAt: null,

    setMode: (mode) => {
      const themeId = resolveThemeId(mode);
      const theme = themeId === "dark" ? darkTheme : lightTheme;
      applyTheme(theme);
      saveMode(mode);
      set({
        mode,
        activeThemeId: themeId,
        switchCount: get().switchCount + 1,
        lastSwitchedAt: new Date().toISOString(),
      });
    },

    toggleMode: () => {
      const current = get().activeThemeId;
      const next = current === "dark" ? "light" : "dark";
      get().setMode(next);
    },

    getEffectiveThemeId: () => {
      return resolveThemeId(get().mode);
    },
  };
});
