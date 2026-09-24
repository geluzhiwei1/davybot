/**
 * 我的设备(桌面能力中继方案 §9.4)— /settings/devices
 *
 * 列出账号下所有桌面设备(davy-light-app):在线状态、label、版本、
 * 最后活跃、能力(server 清单);支持重命名与远程登出(在线设备即时收到
 * device/logout 控制帧:清本地凭证 + 轮换设备身份;浏览器登录态不删)。
 *
 * is_current:桌面 WebView 内经 inject.js shim 读壳侧 /api/mcp-host/status
 * 的 device_id 比对;纯浏览器访问时全部显示为远程设备。
 */
import { createFileRoute } from "@tanstack/react-router";
import { BRAND_NAME } from "@/lib/brand";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CapabilityGate } from "@/components/capability-gate";
import { Laptop, MonitorSmartphone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import {
  listMyDevices,
  renameMyDevice,
  revokeMyDevice,
  type RelayDeviceInfo,
} from "@/lib/desktop-relay";

export const Route = createFileRoute("/settings/devices")({
  component: MyDevicesPage,
});

const IS_DESKTOP = typeof window !== "undefined" && !!(window as { __TAURI__?: unknown }).__TAURI__;

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

// 能力门 (多模式统一方案 §L4): 无 relay capability → 显式空态而非空转
function MyDevicesPage() {
  return (
    <CapabilityGate section="devices">
      <MyDevicesPageInner />
    </CapabilityGate>
  );
}

function MyDevicesPageInner() {
  const [devices, setDevices] = useState<RelayDeviceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [localDeviceId, setLocalDeviceId] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<RelayDeviceInfo | null>(null);
  const [renameText, setRenameText] = useState("");
  const [revoking, setRevoking] = useState<RelayDeviceInfo | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDevices(await listMyDevices());
    } catch (e) {
      toast.error("设备列表加载失败", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 本机设备身份(is_current):桌面 WebView 内经 inject.js shim 走环回;
  // 纯浏览器 fetch 会打到云端 404 → 静默保持"全部远程"。
  useEffect(() => {
    if (!IS_DESKTOP) return;
    fetch("/api/mcp-host/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((v: { device_id?: string } | null) => {
        if (v?.device_id) setLocalDeviceId(v.device_id);
      })
      .catch(() => {});
  }, []);

  const onlineCount = useMemo(
    () => devices.filter((d) => d.online && !d.revoked).length,
    [devices],
  );

  const submitRename = async () => {
    if (!renaming) return;
    const label = renameText.trim();
    if (!label) return;
    setBusyId(renaming.device_id);
    try {
      await renameMyDevice(renaming.device_id, label);
      toast.success(`已重命名为「${label}」`);
      setRenaming(null);
      await load();
    } catch (e) {
      toast.error("重命名失败", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  };

  const submitRevoke = async () => {
    if (!revoking) return;
    setBusyId(revoking.device_id);
    try {
      await revokeMyDevice(revoking.device_id);
      toast.success(`已远程登出「${revoking.label}」`, {
        description: "该设备桌面端将收到登出通知并重置设备身份;浏览器登录态保留在其本机。",
      });
      setRevoking(null);
      await load();
    } catch (e) {
      toast.error("远程登出失败", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-3xl mx-auto px-6 py-10">
        {/* 原「返回设置」按钮随 /settings 枢纽页移除;本页入口 = 用户菜单「我的设备」/ accounts 徽标 */}
        <h1 className="text-2xl font-bold mb-1">我的设备</h1>
        <p className="text-sm text-muted-foreground mb-6">
          登录本账号的桌面版({BRAND_NAME} Light)设备清单。在线设备可被 Web 端远程驱动 (浏览器轨/本机
          MCP);可疑设备可立即远程登出。
        </p>

        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <MonitorSmartphone className="w-5 h-5" />
              设备({devices.length})· 在线 {onlineCount}
            </CardTitle>
            <CardDescription>
              离线判定 = 120s 无心跳;revoked 设备重连即被拒(403)并以新身份重新注册。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading && <p className="text-sm text-muted-foreground">加载中…</p>}
            {!loading && devices.length === 0 && (
              <p className="text-sm text-muted-foreground">
                暂无设备。安装桌面版并登录后,设备会自动出现在这里。
              </p>
            )}
            {devices.map((d) => {
              const isCurrent = localDeviceId === d.device_id;
              return (
                <div
                  key={d.device_id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Laptop className="w-4 h-4 shrink-0 text-muted-foreground" />
                      <span className="text-sm font-medium truncate">{d.label}</span>
                      {isCurrent && <Badge className="text-xs">本机</Badge>}
                      {d.revoked ? (
                        <Badge variant="destructive" className="text-xs">
                          已登出
                        </Badge>
                      ) : d.online ? (
                        <Badge className="bg-green-500/20 text-green-500 text-xs">在线</Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">
                          离线
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground space-y-0.5">
                      <div>
                        最后活跃 {fmtTime(d.last_seen)} · 注册于 {fmtTime(d.registered_at)} · v
                        {d.client_version || "?"}
                      </div>
                      <div className="truncate font-mono" title={d.device_id}>
                        {d.device_id}
                      </div>
                      {d.servers.length > 0 && (
                        <div className="truncate">能力:{d.servers.join(", ")}</div>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busyId === d.device_id}
                      onClick={() => {
                        setRenaming(d);
                        setRenameText(d.label);
                      }}
                    >
                      重命名
                    </Button>
                    {!isCurrent && (
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={busyId === d.device_id || d.revoked}
                        onClick={() => setRevoking(d)}
                      >
                        远程登出
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground">
          远程登出不会删除该设备本机保存的浏览器登录态;设备桌面端会收到系统通知,
          并在下次登录时以全新设备身份重新绑定。
        </p>
      </div>

      {/* 重命名对话框 */}
      <Dialog open={!!renaming} onOpenChange={(v) => !v && setRenaming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名设备</DialogTitle>
            <DialogDescription>
              设备名仅用于识别(如「公司台式机」);桌面端心跳不会覆盖此名称。
            </DialogDescription>
          </DialogHeader>
          <Input
            value={renameText}
            onChange={(e) => setRenameText(e.target.value)}
            maxLength={64}
            placeholder="设备显示名"
            onKeyDown={(e) => e.key === "Enter" && void submitRename()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenaming(null)}>
              取消
            </Button>
            <Button onClick={() => void submitRename()} disabled={!renameText.trim()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 远程登出二次确认(§7.2-5:后果具体,非泛化警告) */}
      <Dialog open={!!revoking} onOpenChange={(v) => !v && setRevoking(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>远程登出「{revoking?.label}」?</DialogTitle>
            <DialogDescription>
              该设备的桌面端会话将立即失效:Web 端不再能驱动它的浏览器轨与本机 MCP
              server,设备身份将被重置。它本机保存的浏览器登录态不受影响。
              若这不是你认识的设备,建议同时修改账号密码。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevoking(null)}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => void submitRevoke()}>
              确认远程登出
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
