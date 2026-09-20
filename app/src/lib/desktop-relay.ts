/**
 * 桌面能力中继(web 版 → 桌面版 davy-light-app)—— 云端 MCP relay API 客户端。
 *
 * 桌面版壳以长轮询在线(register/claim/result,120s 心跳判定);云端提供:
 *   GET  /api/users/me/mcp-relay/servers  在线状态 + 已注册本机 server 清单
 *   POST /api/users/me/mcp-relay/call     web → 桌面 tool 调用(方案 §5.2)
 * 内置 server `dawei-track` 暴露浏览器轨 5 工具(login_open / verify /
 * task_confirm / task_captcha_solve / track_status)。
 *
 * 错误语义(FAST FAIL,后端 detail 已是人话):
 *   409 = 桌面版离线或 server 未注册;429 = 限流(10 次/分);
 *   502 = 工具执行错误;504 = 桌面执行超时(云端等待包络 75s)。
 */
import { ApiError, apiErrorDetail, request } from "@/lib/api/client";

/** dawei-track = 桌面版内置浏览器轨 MCP server(command/env 留在本机)。 */
export const TRACK_SERVER = "dawei-track";

export interface RelayPresence {
  online: boolean;
  last_seen: string | null;
  servers: Array<{ name: string; timeout: number }>;
  /** per-device 视图(§8.2;旧后端可能缺省)。 */
  devices?: RelayDeviceInfo[];
}

/** 「我的设备」条目(GET /api/users/me/devices;§9.4)。 */
export interface RelayDeviceInfo {
  device_id: string;
  label: string;
  client_version: string;
  registered_at: string;
  last_seen: string;
  online: boolean;
  revoked: boolean;
  servers: string[];
}

export interface TrackLoginOpenResult {
  ok: boolean;
  cdp_port: number;
  profile: string;
}

export interface TrackVerifyResult {
  ok: boolean;
  platform: string;
  logged_in: boolean;
}

/** 在线状态探测(页面 30s 轮询,与壳 claim 长轮询节奏对齐)。 */
export async function desktopPresence(): Promise<RelayPresence> {
  return request<RelayPresence>("/api/users/me/mcp-relay/servers", { timeoutMs: 10_000 });
}

/**
 * web → 桌面 tool 调用。timeoutMs=80s:云端等待包络 75s + 余量
 * (浏览器轨 verify 可达数十秒),失败统一抛 Error(relayErrorMessage)。
 * deviceId(§8.3):多桌面时有副作用命令定向指定设备;缺省由云端自动
 * 路由(唯一在线托管设备 → 定向,多台 → 广播)。
 */
export async function relayCall<T = unknown>(
  server: string,
  tool: string,
  args: Record<string, unknown> = {},
  deviceId?: string,
): Promise<T> {
  try {
    const r = await request<{ success: boolean; result: T }>(
      "/api/users/me/mcp-relay/call",
      {
        method: "POST",
        body: JSON.stringify({ server, tool, arguments: args, device_id: deviceId || undefined }),
        timeoutMs: 80_000,
      },
    );
    return r.result;
  } catch (e) {
    throw new Error(relayErrorMessage(e));
  }
}

/** relay 错误 → 可读文案(AbortError 单独映射,其余透传后端 detail)。 */
export function relayErrorMessage(e: unknown): string {
  if (e instanceof Error && e.name === "AbortError")
    return "请求超时(桌面版执行超过 75 秒或网络中断)";
  if (e instanceof ApiError) return apiErrorDetail(e);
  return e instanceof Error ? e.message : String(e);
}

/** 远程打开平台登录窗口(弹出在桌面版所在电脑的 Chrome 中)。 */
export function relayTrackLoginOpen(
  platform: string,
  deviceId?: string,
): Promise<TrackLoginOpenResult> {
  return relayCall<TrackLoginOpenResult>(TRACK_SERVER, "browser_login_open", { platform }, deviceId);
}

/** 远程校验平台登录态(走桌面版 recipe login_check,幂等只读)。 */
export function relayTrackVerify(
  platform: string,
  deviceId?: string,
): Promise<TrackVerifyResult> {
  return relayCall<TrackVerifyResult>(TRACK_SERVER, "browser_verify", { platform }, deviceId);
}

// ── 「我的设备」管理面(方案 §9.3;JWT 同用户,云端 device registry)──

/** 设备清单(在线/离线、label、版本、最后活跃、能力)。 */
export async function listMyDevices(): Promise<RelayDeviceInfo[]> {
  const r = await request<{ success: boolean; devices: RelayDeviceInfo[] }>(
    "/api/users/me/devices",
    { timeoutMs: 10_000 },
  );
  return r.devices ?? [];
}

/** 重命名设备(label 仅此处可改;壳 register 心跳不覆盖)。 */
export function renameMyDevice(deviceId: string, label: string): Promise<void> {
  return request(`/api/users/me/devices/${encodeURIComponent(deviceId)}/rename`, {
    method: "POST",
    body: JSON.stringify({ label }),
    timeoutMs: 10_000,
  }).then(() => undefined);
}

/**
 * 远程登出设备(§9.3):在线设备立即收到 device/logout 控制帧(壳清本地
 * 凭证 + 轮换设备身份);离线设备标记 revoked,重连即 403 登出。
 * 不删桌面本机浏览器登录态。限频 5 次/小时。
 */
export function revokeMyDevice(deviceId: string): Promise<void> {
  return request(`/api/users/me/devices/${encodeURIComponent(deviceId)}`, {
    method: "DELETE",
    timeoutMs: 10_000,
  }).then(() => undefined);
}
