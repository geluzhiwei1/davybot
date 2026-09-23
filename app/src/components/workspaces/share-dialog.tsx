/**
 * WorkspaceShareDialog — 工作区分享 Owner 弹窗（方案 §6）
 *
 * 两态:
 * - 创建态 (GET 404): 选有效期 (仅 1/3/7 天, R6) + 可选自定义提取码 → 生成
 * - 管理态: 链接/提取码复制、状态徽章 (分享中/已关闭/已过期/已撤销)、浏览/复制计数、
 *   续期、关闭/开启、撤销 (永久, AlertDialog)、重新生成 (轮换链接+提取码)、复制记录
 *
 * 文案走 routesB i18n (workspaces.share*)，与 workspaces.tsx 同页一致。
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Copy,
  Eye,
  Link2,
  Loader2,
  Lock,
  RefreshCw,
  RotateCcw,
  Share2,
  Trash2,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiErrorDetail } from "@/lib/api/client";
import { workspaceShareApi, type OwnerShareView, type ShareExpiryDays } from "@/lib/api/share";
import { getBasepath } from "@/router";

const EXPIRY_OPTIONS: ShareExpiryDays[] = [1, 3, 7];

interface WorkspaceShareDialogProps {
  workspaceId: string;
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceShareDialog({
  workspaceId,
  workspaceName,
  open,
  onOpenChange,
}: WorkspaceShareDialogProps) {
  const { t } = useTranslation("routesB");
  /** null = 加载中; "none" = 尚无分享 (创建态); 其余 = 管理态 */
  const [view, setView] = useState<OwnerShareView | "none" | null>(null);
  const [expiry, setExpiry] = useState<ShareExpiryDays>(3);
  const [customPassword, setCustomPassword] = useState("");
  const [busy, setBusy] = useState(false);
  /** 危险操作确认: revoke = 撤销; regenerate = 重新生成 (轮换, 默认 3 天档) */
  const [confirmKind, setConfirmKind] = useState<"revoke" | "regenerate" | null>(null);

  const refresh = useCallback(async () => {
    try {
      const v = await workspaceShareApi.get(workspaceId);
      setView(v);
    } catch (e) {
      // 404 = 该工作区尚未创建分享 → 创建态; 其余报错提示
      if (e && typeof e === "object" && "status" in e && (e as { status: number }).status === 404) {
        setView("none");
      } else {
        setView("none");
        toast.error(t("workspaces.shareLoadFailed"), { description: apiErrorDetail(e) });
      }
    }
  }, [workspaceId, t]);

  useEffect(() => {
    if (!open) return;
    setView(null);
    setCustomPassword("");
    setConfirmKind(null);
    void refresh();
  }, [open, refresh]);

  async function run(action: () => Promise<unknown>, successMsg?: string) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      if (successMsg) toast.success(successMsg);
      await refresh();
    } catch (e) {
      toast.error(apiErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  const handleCreate = () =>
    run(
      () =>
        workspaceShareApi
          .create(workspaceId, expiry, customPassword.trim() || undefined)
          .then(() => {
            setCustomPassword("");
          }),
      t("workspaces.shareCreated"),
    );

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("workspaces.shareCopied"));
    } catch {
      toast.error(t("workspaces.shareCopyFailed"));
    }
  };

  const fullLink =
    view && view !== "none" ? `${window.location.origin}${getBasepath()}${view.url}` : "";
  const fmtTime = (iso?: string) =>
    iso
      ? new Date(iso).toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Share2 className="w-4 h-4 text-brand" />
            {t("workspaces.shareTitle", { name: workspaceName })}
          </DialogTitle>
          {!view || view === "none" ? (
            <DialogDescription>{t("workspaces.shareCreateDesc")}</DialogDescription>
          ) : (
            <DialogDescription>{t("workspaces.shareManageDesc")}</DialogDescription>
          )}
        </DialogHeader>

        {view === null ? (
          <div className="flex justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : view === "none" ? (
          /* ── 创建态 ── */
          <div className="space-y-4 py-1">
            <div>
              <p className="text-sm font-medium mb-2">{t("workspaces.shareExpiryLabel")}</p>
              <div className="grid grid-cols-3 gap-2">
                {EXPIRY_OPTIONS.map((d) => (
                  <Button
                    key={d}
                    type="button"
                    variant={expiry === d ? "default" : "outline"}
                    className={expiry === d ? "bg-gradient-brand text-brand-foreground" : ""}
                    onClick={() => setExpiry(d)}
                  >
                    {t("workspaces.shareDays", { count: d })}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">{t("workspaces.shareCustomPassword")}</p>
              <Input
                placeholder={t("workspaces.shareAutoPassword")}
                value={customPassword}
                onChange={(e) => setCustomPassword(e.target.value)}
                maxLength={32}
              />
            </div>
            <Button
              className="w-full bg-gradient-brand text-brand-foreground"
              onClick={handleCreate}
              disabled={busy}
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : t("workspaces.shareCreateBtn")}
            </Button>
          </div>
        ) : (
          /* ── 管理态 ── */
          <div className="space-y-4 py-1">
            {/* 状态行 */}
            <div className="flex flex-wrap items-center gap-2">
              {view.revoked ? (
                <Badge variant="destructive" className="text-[11px]">
                  {t("workspaces.shareStatusRevoked")}
                </Badge>
              ) : view.expired ? (
                <Badge variant="outline" className="text-[11px] text-amber-600 border-amber-300">
                  {t("workspaces.shareStatusExpired")}
                </Badge>
              ) : view.status === "active" ? (
                <Badge className="bg-emerald-500/15 text-emerald-600 border-0 text-[11px]">
                  {t("workspaces.shareStatusActive")}
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-[11px]">
                  {t("workspaces.shareStatusClosed")}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {t("workspaces.shareExpiresAt", { time: fmtTime(view.expires_at) })}
              </span>
              <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                <Eye className="w-3 h-3" /> {view.view_count}
                <span className="mx-1">·</span>
                <Copy className="w-3 h-3" /> {view.clone_count}
              </span>
            </div>

            {/* 链接 + 提取码 */}
            {!view.revoked && (
              <>
                <div className="space-y-1.5">
                  <p className="text-xs font-medium flex items-center gap-1">
                    <Link2 className="w-3 h-3" /> {t("workspaces.shareLinkLabel")}
                  </p>
                  <div className="flex gap-2">
                    <Input
                      readOnly
                      value={fullLink}
                      className="text-xs h-9"
                      onFocus={(e) => e.target.select()}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 shrink-0 gap-1"
                      onClick={() => void handleCopy(fullLink)}
                    >
                      <Copy className="w-3 h-3" /> {t("workspaces.shareCopy")}
                    </Button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <p className="text-xs font-medium flex items-center gap-1">
                    <Lock className="w-3 h-3" /> {t("workspaces.sharePasswordLabel")}
                  </p>
                  {view.password ? (
                    <div className="flex gap-2">
                      <Input
                        readOnly
                        value={view.password}
                        className="text-xs h-9 tracking-[0.3em] text-center font-mono"
                        onFocus={(e) => e.target.select()}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-9 shrink-0 gap-1"
                        onClick={() => void handleCopy(view.password || "")}
                      >
                        <Copy className="w-3 h-3" /> {t("workspaces.shareCopy")}
                      </Button>
                    </div>
                  ) : (
                    <p className="text-xs text-amber-600">
                      {t("workspaces.sharePasswordUnavailable")}
                    </p>
                  )}
                </div>
              </>
            )}

            {/* 操作区: 仅未撤销时 */}
            {!view.revoked && (
              <div className="space-y-2 border-t border-border pt-3">
                {/* 续期: 三档行内选 */}
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="text-xs text-muted-foreground shrink-0">
                    {t("workspaces.shareRenew")}
                  </span>
                  <div className="flex gap-1.5 ml-auto">
                    {EXPIRY_OPTIONS.map((d) => (
                      <Button
                        key={d}
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2.5 text-xs"
                        disabled={busy}
                        onClick={() => run(() => workspaceShareApi.updateExpiry(workspaceId, d))}
                      >
                        {t("workspaces.shareDays", { count: d })}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  {view.status === "active" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 flex-1"
                      disabled={busy}
                      onClick={() => run(() => workspaceShareApi.close(workspaceId))}
                    >
                      <Eye className="w-3.5 h-3.5" /> {t("workspaces.shareClose")}
                    </Button>
                  ) : view.expired ? (
                    <div className="flex items-center gap-1.5 flex-1">
                      <span className="text-xs text-muted-foreground">
                        {t("workspaces.shareReopenWithDays")}
                      </span>
                      {EXPIRY_OPTIONS.map((d) => (
                        <Button
                          key={d}
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 px-2.5 text-xs"
                          disabled={busy}
                          onClick={() => run(() => workspaceShareApi.open(workspaceId, d))}
                        >
                          {t("workspaces.shareDays", { count: d })}
                        </Button>
                      ))}
                    </div>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 flex-1"
                      disabled={busy}
                      onClick={() => run(() => workspaceShareApi.open(workspaceId))}
                    >
                      <Eye className="w-3.5 h-3.5" /> {t("workspaces.shareOpen")}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    disabled={busy}
                    onClick={() => setConfirmKind("regenerate")}
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> {t("workspaces.shareRegenerate")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 text-destructive hover:text-destructive"
                    disabled={busy}
                    onClick={() => setConfirmKind("revoke")}
                  >
                    <Trash2 className="w-3.5 h-3.5" /> {t("workspaces.shareRevoke")}
                  </Button>
                </div>
              </div>
            )}

            {/* 复制记录 */}
            <div className="border-t border-border pt-3">
              <p className="text-xs font-medium mb-1.5">{t("workspaces.shareCloneLog")}</p>
              {view.clone_log.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {t("workspaces.shareCloneLogEmpty")}
                </p>
              ) : (
                <ul className="max-h-28 overflow-y-auto scrollbar-thin space-y-1">
                  {view.clone_log.map((entry, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Copy className="w-3 h-3 shrink-0" />
                      <span>{entry.user}</span>
                      <span className="ml-auto">{fmtTime(entry.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </DialogContent>

      {/* 危险操作确认 */}
      <AlertDialog open={confirmKind !== null} onOpenChange={(o) => !o && setConfirmKind(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className={confirmKind === "revoke" ? "text-destructive" : ""}>
              {confirmKind === "revoke"
                ? t("workspaces.shareRevokeTitle")
                : t("workspaces.shareRegenerateTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmKind === "revoke"
                ? t("workspaces.shareRevokeDesc")
                : t("workspaces.shareRegenerateDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("workspaces.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className={
                confirmKind === "revoke"
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : ""
              }
              onClick={() => {
                if (confirmKind === "revoke") void run(() => workspaceShareApi.revoke(workspaceId));
                else if (confirmKind === "regenerate")
                  void run(() => workspaceShareApi.create(workspaceId, 3));
                setConfirmKind(null);
              }}
            >
              {confirmKind === "revoke"
                ? t("workspaces.shareRevoke")
                : t("workspaces.shareRegenerate")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
