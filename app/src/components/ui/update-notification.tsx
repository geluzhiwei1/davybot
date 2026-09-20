/**
 * UpdateNotification — 桌面应用更新提示弹窗
 *
 * 展示三个用户选项：立即更新 / 稍后提醒 / 跳过此版本
 * 下载中显示进度条，完成后提示重启。
 *
 * 仅在 Tauri 环境下渲染（通过 useUpdate hook 内部检测）。
 */
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { useUpdate } from "@/hooks/use-update";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export function UpdateNotification() {
  const { t } = useTranslation("miscUi");
  const {
    updateAvailable,
    updateVersion,
    updateNotes,
    currentVersion,
    forced,
    downloading,
    downloadProgress,
    error,
    dialogOpen,
    status,
    downloadAndInstall,
    skipVersion,
    remindLater,
    dismissError,
    setDialogOpen,
  } = useUpdate();

  // ── 没有更新或弹窗未打开时不渲染 ───────────────────────
  if (!dialogOpen) return null;

  // ── 错误状态 ───────────────────────────────────────────
  if (status === "error") {
    return (
      <Dialog open onOpenChange={dismissError}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("update.checkFailed")}</DialogTitle>
            <DialogDescription>{error || t("update.networkError")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={dismissError}>
              {t("update.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // ── 下载中 ─────────────────────────────────────────────
  if (status === "downloading") {
    return (
      <Dialog open onOpenChange={() => {}}>
        <DialogContent className="max-w-md" onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Download className="h-5 w-5 animate-pulse" />
              {t("update.downloadingTitle")}
            </DialogTitle>
            <DialogDescription>NormNomos v{updateVersion}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Progress value={downloadProgress} className="h-3" />
            <p className="text-center text-xs text-muted-foreground">
              {downloadProgress > 0 ? `${Math.round(downloadProgress)}%` : t("update.preparing")}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  // ── 安装就绪（patch 自动下载完成） ──────────────────────
  if (status === "ready") {
    return (
      <Dialog open onOpenChange={() => {}}>
        <DialogContent className="max-w-md" onInteractOutside={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Download className="h-5 w-5 text-green-500" />
              {t("update.readyTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("update.readyDesc", { version: updateVersion })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              {t("update.restartLater")}
            </Button>
            <Button
              onClick={() => {
                // App will restart via Rust after install
                setDialogOpen(false);
              }}
            >
              {t("update.restartNow")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // ── 更新可用（默认展示） ───────────────────────────────
  if (!updateAvailable || !updateVersion) return null;

  return (
    <Dialog open onOpenChange={forced ? () => {} : () => setDialogOpen(false)}>
      <DialogContent
        className="max-w-lg"
        onInteractOutside={forced ? (e) => e.preventDefault() : undefined}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              {forced && (
                <span className="text-xs font-bold bg-destructive/10 text-destructive px-2 py-0.5 rounded">
                  {t("update.important")}
                </span>
              )}
              {t("update.newVersion", { version: updateVersion })}
            </span>
            {currentVersion && (
              <span className="text-sm font-normal text-muted-foreground">
                {t("update.currentVersion", { version: currentVersion })}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            {forced ? t("update.forcedDesc") : t("update.normalDesc")}
          </DialogDescription>
        </DialogHeader>

        {/* Release Notes */}
        {updateNotes && (
          <div className="max-h-64 overflow-y-auto rounded-md border bg-muted/50 p-3 text-sm prose prose-sm dark:prose-invert">
            <div
              className="whitespace-pre-wrap"
              dangerouslySetInnerHTML={{
                __html: updateNotes
                  .replace(/&/g, "&amp;")
                  .replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;")
                  .replace(/## /g, "<strong>")
                  .replace(/\n/g, "<br/>"),
              }}
            />
          </div>
        )}

        <DialogFooter className="flex flex-col gap-2 sm:flex-row sm:justify-between sm:gap-0">
          <div className="flex gap-2">
            {!forced && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={skipVersion}
                  className="text-muted-foreground"
                >
                  {t("update.skipVersion")}
                </Button>
                <Button variant="ghost" size="sm" onClick={remindLater}>
                  {t("update.remindLater")}
                </Button>
              </>
            )}
          </div>
          <Button onClick={downloadAndInstall} disabled={downloading}>
            <Download className={cn("h-4 w-4", downloading && "animate-spin")} />
            {downloading ? t("update.downloading") : t("update.updateNow")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
