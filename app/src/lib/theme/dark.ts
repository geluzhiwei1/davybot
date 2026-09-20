/**
 * Dark theme configuration — matches existing styles.css oklch values
 */
import type { ThemeConfig } from "./types";

export const darkTheme: ThemeConfig = {
  id: "dark",
  name: "Dark",
  description: "深色主题 — 护眼舒适",
  colors: {
    primary: "oklch(0.78 0.15 215)",
    secondary: "oklch(0.28 0.035 252)",
    accent: "oklch(0.32 0.05 230)",
    success: "oklch(0.7 0.18 145)",
    warning: "oklch(0.7 0.18 45)",
    error: "oklch(0.62 0.22 25)",
    info: "oklch(0.72 0.16 220)",
    bgPrimary: "oklch(0.18 0.025 250)",
    bgSecondary: "oklch(0.22 0.03 250)",
    bgTertiary: "oklch(0.26 0.03 252)",
    textPrimary: "oklch(0.97 0.01 240)",
    textSecondary: "oklch(0.92 0.012 240)",
    textTertiary: "oklch(0.68 0.025 248)",
    border: "oklch(1 0 0 / 8%)",
    borderLight: "oklch(1 0 0 / 12%)",
    overlay: "oklch(0 0 0 / 75%)",
  },
  fonts: {
    family:
      '"Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif',
    familyMono: '"Consolas", "Monaco", "Courier New", monospace',
    size: { xs: "12px", sm: "13px", md: "14px", lg: "16px", xl: "18px" },
    weight: { normal: 400, medium: 500, bold: 700 },
  },
};
