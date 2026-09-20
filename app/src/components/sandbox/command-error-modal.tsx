/**
 * CommandErrorModal — ro 模式写命令错误展示 + 跳转设置 (§14.3)
 * 父组件 (错误触发) 通过 props 控制
 *
 * §14.8 错误码到 UI 映射
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TriangleAlert, Settings, RefreshCw, LifeBuoy } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SandboxError, SandboxErrorCode } from "@/lib/types/sandbox";

interface CommandErrorModalProps {
  error: SandboxError | null;
  onDismiss: () => void;
  onNavigate?: (target: string) => void;
  onRetry?: () => void;
}

const ERROR_CONFIG: Record<
  SandboxErrorCode,
  {
    title: string;
    variant: "default" | "destructive";
    action: "open_settings" | "contact_admin" | "retry";
  }
> = {
  RO_MODE_WRITE_DENIED: {
    title: "error.RO_MODE_WRITE_DENIED.title",
    variant: "default",
    action: "open_settings",
  },
  QUOTA_EXCEEDED: {
    title: "error.QUOTA_EXCEEDED.title",
    variant: "destructive",
    action: "open_settings",
  },
  PATH_OUT_OF_ALLOWLIST: {
    title: "error.PATH_OUT_OF_ALLOWLIST.title",
    variant: "destructive",
    action: "contact_admin",
  },
  TMPFS_MASK_FAILED: {
    title: "error.TMPFS_MASK_FAILED.title",
    variant: "destructive",
    action: "contact_admin",
  },
  TRUSTED_CONTEXT_EXPIRED: {
    title: "error.TRUSTED_CONTEXT_EXPIRED.title",
    variant: "default",
    action: "open_settings",
  },
  NETWORK_DENIED: {
    title: "error.NETWORK_DENIED.title",
    variant: "default",
    action: "open_settings",
  },
  SANDBOX_TIMEOUT: {
    title: "error.SANDBOX_TIMEOUT.title",
    variant: "destructive",
    action: "retry",
  },
  UNKNOWN: {
    title: "error.UNKNOWN.title",
    variant: "destructive",
    action: "retry",
  },
};

export function CommandErrorModal({
  error,
  onDismiss,
  onNavigate,
  onRetry,
}: CommandErrorModalProps) {
  const { t } = useTranslation("sandbox");
  const isOpen = error !== null;
  const config = error ? ERROR_CONFIG[error.code] : null;

  function handleAction() {
    if (!error || !config) return;
    if (config.action === "retry" && onRetry) {
      onRetry();
    } else if (onNavigate) {
      onNavigate(config.action === "open_settings" ? "/settings/security" : "");
    }
    onDismiss();
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onDismiss()}>
      <DialogContent
        role="alertdialog"
        className="max-w-md"
        onOpenAutoFocus={(e) => {
          // 焦点初始在关闭/操作按钮, 而非内容
          e.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TriangleAlert
              className={`h-5 w-5 ${config?.variant === "destructive" ? "text-destructive" : "text-yellow-500"}`}
            />
            {config ? t(config.title) : t("error.defaultTitle")}
          </DialogTitle>
          {error?.message && <DialogDescription>{error.message}</DialogDescription>}
        </DialogHeader>

        {error?.exit_code !== undefined && (
          <p className="text-sm text-muted-foreground">
            {t("error.exitCode", { code: error.exit_code })}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onDismiss}>
            {t("error.action.close")}
          </Button>
          {config && (
            <Button
              onClick={handleAction}
              variant={config.variant === "destructive" ? "destructive" : "default"}
            >
              {config.action === "open_settings" && <Settings className="mr-2 h-4 w-4" />}
              {config.action === "contact_admin" && <LifeBuoy className="mr-2 h-4 w-4" />}
              {config.action === "retry" && <RefreshCw className="mr-2 h-4 w-4" />}
              {t(`error.action.${config.action}`)}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
