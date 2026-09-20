/**
 * Theme hook — convenience wrapper around useThemeStore.
 * Migrated from legalbot/webui/src/themes/composables/useTheme.ts
 */
import { useThemeStore } from "../lib/theme-store";
import { darkTheme, lightTheme, getSystemTheme } from "../lib/theme";

export function useTheme() {
  const {
    mode,
    activeThemeId,
    switchCount,
    lastSwitchedAt,
    setMode,
    toggleMode,
    getEffectiveThemeId,
  } = useThemeStore();

  const isDark = activeThemeId === "dark";
  const currentTheme = isDark ? darkTheme : lightTheme;

  return {
    mode,
    activeThemeId: getEffectiveThemeId(),
    isDark,
    currentTheme,
    switchCount,
    lastSwitchedAt,
    setMode,
    toggleMode,
    setDark: () => setMode("dark"),
    setLight: () => setMode("light"),
    setSystem: () => setMode("system"),
    systemPreference: getSystemTheme(),
  };
}
