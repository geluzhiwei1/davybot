/**
 * Theme type definitions — migrated from legalbot/webui/src/themes/types.ts
 */

export type ThemeMode = "dark" | "light" | "system";

export interface ThemeColors {
  primary: string;
  secondary: string;
  accent: string;
  success: string;
  warning: string;
  error: string;
  info: string;
  bgPrimary: string;
  bgSecondary: string;
  bgTertiary: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  border: string;
  borderLight: string;
  overlay: string;
}

export interface FontConfig {
  family: string;
  familyMono: string;
  size: Record<string, string>;
  weight: Record<string, number>;
}

export interface ThemeConfig {
  id: string;
  name: string;
  description: string;
  colors: ThemeColors;
  fonts: FontConfig;
}

export interface ThemeCSSVariables {
  [key: string]: string;
}
