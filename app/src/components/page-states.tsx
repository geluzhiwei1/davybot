/**
 * Unified page state components — §4.9
 * Standardized loading / empty / error states for all pages.
 */
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Loader2, AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// ─── Loading Skeleton ──────────────────────────────────────────

interface LoadingSkeletonProps {
  /** Number of skeleton rows (default 5) */
  rows?: number;
  /** Show card-style skeleton (default: list-style) */
  variant?: "list" | "card" | "table";
  className?: string;
}

export function LoadingSkeleton({ rows = 5, variant = "list", className }: LoadingSkeletonProps) {
  if (variant === "card") {
    return (
      <div className={`grid grid-cols-2 md:grid-cols-3 gap-4 ${className || ""}`}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="rounded-lg border p-4 space-y-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div className={`space-y-2 ${className || ""}`}>
        <Skeleton className="h-9 w-full" />
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    );
  }

  // list variant (default)
  return (
    <div className={`space-y-3 ${className || ""}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-9 w-9 rounded-full shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Full-page Loading ─────────────────────────────────────────

interface LoadingPageProps {
  message?: string;
}

export function LoadingPage({ message }: LoadingPageProps) {
  const { t } = useTranslation("commonUi");
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
      <Loader2 className="w-6 h-6 animate-spin" />
      <p className="text-sm">{message ?? t("page.loading")}</p>
    </div>
  );
}

// ─── Empty State ───────────────────────────────────────────────

interface EmptyStateProps {
  /** Icon to display (default Inbox) */
  icon?: LucideIcon;
  /** Primary message */
  title: string;
  /** Secondary description */
  description?: string;
  /** Optional action button */
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center h-full gap-3 text-center px-4 ${className || ""}`}
    >
      <Icon className="w-10 h-10 text-muted-foreground/30" />
      <div className="space-y-1">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        {description && <p className="text-xs text-muted-foreground/70 max-w-xs">{description}</p>}
      </div>
      {action && (
        <Button size="sm" onClick={action.onClick} className="mt-1">
          {action.label}
        </Button>
      )}
    </div>
  );
}

// ─── Error State ───────────────────────────────────────────────

interface ErrorStateProps {
  /** Error message to display */
  message?: string;
  /** Optional retry callback */
  onRetry?: () => void;
  /** Optional detail text */
  detail?: string;
  className?: string;
}

export function ErrorState({ message, onRetry, detail, className }: ErrorStateProps) {
  const { t } = useTranslation("commonUi");
  return (
    <div
      className={`flex flex-col items-center justify-center h-full gap-3 text-center px-4 ${className || ""}`}
    >
      <AlertCircle className="w-10 h-10 text-destructive/40" />
      <div className="space-y-1">
        <p className="text-sm font-medium text-destructive">{message ?? t("page.loadFailed")}</p>
        {detail && <p className="text-xs text-muted-foreground max-w-xs">{detail}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

// ─── Async Page Wrapper ────────────────────────────────────────

export type AsyncStatus = "idle" | "loading" | "success" | "error";

interface AsyncPageProps {
  status: AsyncStatus;
  error?: string | null;
  data?: unknown;
  /** Show loading skeleton instead of spinner */
  skeleton?: boolean;
  skeletonVariant?: LoadingSkeletonProps["variant"];
  emptyCheck?: (data: unknown) => boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: { label: string; onClick: () => void };
  onRetry?: () => void;
  children: React.ReactNode;
}

/**
 * Unified async page wrapper that handles all four states:
 * idle/loading → spinner/skeleton
 * error → ErrorState
 * success + empty → EmptyState
 * success + data → children
 */
export function AsyncPage({
  status,
  error,
  data,
  skeleton,
  skeletonVariant,
  emptyCheck,
  emptyTitle,
  emptyDescription,
  emptyAction,
  onRetry,
  children,
}: AsyncPageProps) {
  const { t } = useTranslation("commonUi");
  if (status === "loading") {
    if (skeleton) {
      return <LoadingSkeleton variant={skeletonVariant || "list"} />;
    }
    return <LoadingPage />;
  }

  if (status === "error") {
    return <ErrorState message={error || undefined} onRetry={onRetry} />;
  }

  if (emptyCheck && data != null && emptyCheck(data)) {
    return (
      <EmptyState
        title={emptyTitle ?? t("page.noData")}
        description={emptyDescription}
        action={emptyAction}
      />
    );
  }

  if (status === "idle") {
    return <LoadingPage />;
  }

  return <>{children}</>;
}
