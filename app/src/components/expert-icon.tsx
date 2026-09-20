import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  /** Emoji icon string (from team_zh-CN.yaml). Takes priority over LucideIcon. */
  emoji?: string;
  /** Lucide icon — kept for backward compat (custom agents, drawer) */
  icon?: LucideIcon;
  /** HSL hue for LucideIcon gradient background. Ignored when emoji is set. */
  hue?: number;
  size?: "sm" | "md" | "lg";
  shape?: "rounded" | "circle";
  className?: string;
}

const sizeMap = {
  sm: "w-8 h-8",
  md: "w-12 h-12",
  lg: "w-16 h-16",
};

const emojiSize = {
  sm: "text-sm",
  md: "text-lg",
  lg: "text-xl",
} as const;

const radiusMap = {
  sm: "rounded-lg",
  md: "rounded-xl",
  lg: "rounded-xl",
};

/** Category → HSL hue for emoji backgrounds */
const CATEGORY_HUE: Record<string, number> = {
  compliance: 215,
  "intellectual-property": 280,
  "law-firm-management": 170,
};

export function ExpertIcon({
  emoji,
  icon: LucideIcon,
  hue = 215,
  size = "md",
  shape = "rounded",
  className,
}: Props) {
  const radius = shape === "circle" ? "rounded-full" : radiusMap[size];

  // Emoji mode: render emoji text with a colored background
  if (emoji) {
    const bg = `linear-gradient(135deg, oklch(0.6 0.14 ${hue}), oklch(0.78 0.1 ${(hue + 30) % 360}))`;
    return (
      <div
        className={cn(
          "flex items-center justify-center shadow-sm ring-1 ring-white/10 relative overflow-hidden",
          radius,
          sizeMap[size],
          emojiSize[size],
          className,
        )}
        style={{ background: bg }}
      >
        <span
          aria-hidden
          className="absolute inset-0 bg-gradient-to-b from-white/15 to-transparent pointer-events-none"
        />
        <span className="relative">{emoji}</span>
      </div>
    );
  }

  // LucideIcon mode (backward compat)
  const iconSizes = { sm: 15, md: 20, lg: 28 } as const;
  const bg = `linear-gradient(135deg, oklch(0.6 0.14 ${hue}), oklch(0.78 0.1 ${(hue + 30) % 360}))`;
  const LucideComp = LucideIcon;

  return (
    <div
      className={cn(
        "flex items-center justify-center text-white shadow-sm ring-1 ring-white/10 relative overflow-hidden",
        radius,
        sizeMap[size],
        className,
      )}
      style={{ background: bg }}
    >
      <span
        aria-hidden
        className="absolute inset-0 bg-gradient-to-b from-white/15 to-transparent pointer-events-none"
      />
      {LucideComp && <LucideComp size={iconSizes[size]} strokeWidth={2} className="relative" />}
    </div>
  );
}

/** Get a category-based hue for use with emoji icons */
export function getCategoryHue(category: string): number {
  return CATEGORY_HUE[category] ?? 215;
}
