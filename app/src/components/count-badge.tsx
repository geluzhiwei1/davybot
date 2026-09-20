/**
 * CountBadge — tiny pill for sidebar navigation items.
 *
 * Variants:
 *   - count  → blue pill with a number (only renders if count > 0)
 *   - beta   → amber pill with "Beta" text
 *   - alert  → red pill with a number (for overdue/urgent counts)
 */
import { cn } from "@/lib/utils";

interface CountBadgeProps {
  count: number;
  variant?: "count" | "alert";
}

export function CountBadge({ count, variant = "count" }: CountBadgeProps) {
  if (count <= 0) return null;

  return (
    <span
      className={cn(
        "ml-auto text-[10px] px-1.5 py-0.5 rounded-full font-medium tabular-nums",
        variant === "alert"
          ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
          : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
      )}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

export function BetaBadge() {
  return (
    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400 font-medium">
      Beta
    </span>
  );
}

export function AlphaBadge() {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-400 font-medium">
      Alpha
    </span>
  );
}
