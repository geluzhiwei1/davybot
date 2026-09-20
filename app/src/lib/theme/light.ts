/**
 * Light theme configuration — clean, high-contrast light mode
 */
import type { ThemeConfig } from "./types";

export const lightTheme: ThemeConfig = {
  id: "light",
  name: "Light",
  description: "明亮主题 — 清爽明亮",
  colors: {
    primary: "oklch(0.55 0.18 250)",
    secondary: "oklch(0.92 0.02 250)",
    accent: "oklch(0.9 0.04 250)",
    success: "oklch(0.55 0.17 145)",
    warning: "oklch(0.7 0.17 55)",
    error: "oklch(0.58 0.22 25)",
    info: "oklch(0.55 0.16 240)",
    bgPrimary: "oklch(0.99 0.002 250)",
    bgSecondary: "oklch(0.96 0.005 250)",
    bgTertiary: "oklch(0.94 0.008 250)",
    textPrimary: "oklch(0.2 0.02 250)",
    textSecondary: "oklch(0.35 0.015 250)",
    textTertiary: "oklch(0.55 0.015 250)",
    border: "oklch(0.85 0.01 250)",
    borderLight: "oklch(0.9 0.005 250)",
    overlay: "oklch(0 0 0 / 50%)",
  },
  fonts: {
    family:
      '"Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif',
    familyMono: '"Consolas", "Monaco", "Courier New", monospace',
    size: { xs: "12px", sm: "13px", md: "14px", lg: "16px", xl: "18px" },
    weight: { normal: 400, medium: 500, bold: 700 },
  },
};
