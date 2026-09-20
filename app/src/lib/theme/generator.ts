/**
 * Theme CSS variable generator — migrated from legalbot/webui/src/themes/generator.ts
 * Converts theme configurations to CSS variables that work with shadcn/ui's CSS variable system.
 */
import type { ThemeConfig, ThemeCSSVariables } from "./types";

/**
 * Generate shadcn/ui-compatible CSS variables from a theme config.
 * Maps to the same variable names used in styles.css.
 */
export function generateCSSVariables(theme: ThemeConfig): ThemeCSSVariables {
  const vars: ThemeCSSVariables = {};

  // Background & foreground
  vars["--background"] = theme.colors.bgPrimary;
  vars["--foreground"] = theme.colors.textPrimary;

  // Card
  vars["--card"] = theme.colors.bgSecondary;
  vars["--card-foreground"] = theme.colors.textPrimary;

  // Popover
  vars["--popover"] = theme.colors.bgSecondary;
  vars["--popover-foreground"] = theme.colors.textPrimary;

  // Primary
  vars["--primary"] = theme.colors.primary;
  vars["--primary-foreground"] =
    theme.id === "dark" ? "oklch(0.16 0.03 250)" : "oklch(0.98 0.002 250)";

  // Secondary
  vars["--secondary"] = theme.colors.secondary;
  vars["--secondary-foreground"] = theme.colors.textPrimary;

  // Muted
  vars["--muted"] = theme.colors.bgTertiary;
  vars["--muted-foreground"] = theme.colors.textTertiary;

  // Accent
  vars["--accent"] = theme.colors.accent;
  vars["--accent-foreground"] = theme.colors.textPrimary;

  // Destructive
  vars["--destructive"] = theme.colors.error;
  vars["--destructive-foreground"] = "oklch(0.98 0.01 240)";

  // Border, input, ring
  vars["--border"] = theme.colors.border;
  vars["--input"] = theme.colors.borderLight;
  vars["--ring"] = theme.colors.primary;

  // Brand
  vars["--brand"] = theme.colors.primary;
  vars["--brand-foreground"] = vars["--primary-foreground"];
  vars["--brand-glow"] = theme.colors.primary;

  // Sidebar
  vars["--sidebar"] = theme.id === "dark" ? "oklch(0.16 0.025 252)" : "oklch(0.97 0.003 250)";
  vars["--sidebar-foreground"] = theme.colors.textSecondary;
  vars["--sidebar-primary"] = theme.colors.primary;
  vars["--sidebar-primary-foreground"] = vars["--primary-foreground"];
  vars["--sidebar-accent"] = theme.colors.accent;
  vars["--sidebar-accent-foreground"] = theme.colors.textPrimary;
  vars["--sidebar-border"] = theme.colors.border;
  vars["--sidebar-ring"] = theme.colors.primary;

  // Radius
  vars["--radius"] = "0.75rem";

  // Gradients, shadows — theme-aware
  const isDark = theme.id === "dark";
  if (isDark) {
    vars["--gradient-brand"] =
      "linear-gradient(135deg, oklch(0.72 0.16 220), oklch(0.85 0.13 195))";
    vars["--gradient-card"] =
      "linear-gradient(160deg, oklch(0.24 0.04 252 / 0.9), oklch(0.2 0.03 250 / 0.7))";
    vars["--gradient-hero"] =
      "radial-gradient(ellipse at top, oklch(0.32 0.08 220 / 0.45), transparent 60%)";
    vars["--shadow-brand"] = "0 10px 40px -10px oklch(0.72 0.16 220 / 0.5)";
    vars["--shadow-card"] = "0 8px 32px -12px oklch(0 0 0 / 0.4)";
    vars["--color-scheme"] = "dark";
    vars["--glass-bg"] = "oklch(0.22 0.03 252 / 0.55)";
  } else {
    vars["--gradient-brand"] = "linear-gradient(135deg, oklch(0.55 0.18 250), oklch(0.6 0.15 210))";
    vars["--gradient-card"] =
      "linear-gradient(160deg, oklch(0.99 0.003 250), oklch(0.96 0.005 250))";
    vars["--gradient-hero"] =
      "radial-gradient(ellipse at top, oklch(0.92 0.03 250 / 0.3), transparent 60%)";
    vars["--shadow-brand"] = "0 10px 40px -10px oklch(0.55 0.18 250 / 0.2)";
    vars["--shadow-card"] = "0 8px 32px -12px oklch(0 0 0 / 0.08)";
    vars["--color-scheme"] = "light";
    vars["--glass-bg"] = "oklch(0.96 0.005 250 / 0.75)";
  }

  return vars;
}

/**
 * Apply theme CSS variables to document root.
 */
export function applyTheme(theme: ThemeConfig): void {
  if (typeof document === "undefined") return;
  const vars = generateCSSVariables(theme);
  const root = document.documentElement;

  Object.entries(vars).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });

  // Set dark class for shadcn/ui dark variant
  if (theme.id === "dark") {
    root.classList.add("dark");
    root.classList.remove("light");
    root.style.colorScheme = "dark";
  } else {
    root.classList.remove("dark");
    root.classList.add("light");
    root.style.colorScheme = "light";
  }

  // 同步浏览器 chrome 颜色(PWA 地址栏/系统状态栏)。theme-color 不支持
  // oklch,取 bgPrimary 的近似 hex(dark≈#0f1622 / light≈#fbfcfd,
  // 对应 dark.ts / light.ts)。
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if (themeColorMeta) {
    themeColorMeta.setAttribute("content", theme.id === "dark" ? "#0f1622" : "#fbfcfd");
  }
}

/**
 * Remove all theme CSS variables.
 */
export function removeTheme(): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const vars = generateCSSVariables({
    id: "clean",
    name: "",
    description: "",
    colors: {} as never,
    fonts: {} as never,
  });
  Object.keys(vars).forEach((key) => {
    root.style.removeProperty(key);
  });
}

/**
 * Get system color scheme preference.
 */
export function getSystemTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
