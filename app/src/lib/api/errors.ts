/**
 * 智能律所错误翻译层(可用性升级 v1.1 · 域 4.2 / 红线 R1)。
 *
 * 背景:页面此前的 `err instanceof Error ? err.message : t("x")` 方向反了 ——
 * ApiError extends Error 且 message 是英文技术串(`API Error 422: ...`),
 * 真实 API 错误反而优先直出。本层把方向正过来:
 *
 *   apiErrorMessage(err) ?? t("x")   // 翻译优先,页面 i18n 只是兜底
 *
 * 规则(对齐市场线 lib/market/errors.ts):
 * 1. ApiError 先按后端 detail 关键词映射(英文技术词 → 人话);
 * 2. 后端中文业务文案(FastAPI detail)本身面向用户,原样透传;
 * 3. 其余按 HTTP 状态类别给出「发生了什么 + 下一步」;
 * 4. 网络类异常(TypeError / AbortError / fetch failed)统一网络文案;
 * 5. 返回 null 表示无法判定(本地异常/未知),由调用方 i18n 兜底。
 */
import i18n from "../i18n";
import { ApiError } from "./client";

const CJK = /[一-鿿]/;

/** 后端英文 detail 关键词 → apiErrors 文案 key(命中即替换,不透传原文)。 */
const DETAIL_OVERRIDES: Array<[RegExp, string]> = [
  [/not authenticated|unauthorized|invalid token/i, "auth"],
  [/permission denied|forbidden/i, "forbidden"],
  [/not ?found/i, "notFound"],
  [/invalid (status )?transition|illegal transition/i, "invalidTransition"],
  [/insufficient/i, "insufficient"],
  [/already (exists|approved|rejected|converted|archived|transferred)/i, "conflict"],
  [/validation|unprocessable|invalid input/i, "validation"],
];

/** HTTP 状态 → apiErrors 文案 key。 */
function statusKind(status: number): string {
  if (status === 401) return "auth";
  if (status === 403) return "forbidden";
  if (status === 404) return "notFound";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status >= 500) return "server";
  return "unknown";
}

/** 解析 FastAPI `{"detail": ...}` 响应体(对齐 client.ts apiErrorDetail,含 body 非 JSON 兜底)。 */
function parseDetail(e: ApiError): string {
  if (!e.body) return "";
  try {
    const parsed: unknown = JSON.parse(e.body);
    if (parsed && typeof (parsed as { detail?: unknown }).detail === "string") {
      return (parsed as { detail: string }).detail;
    }
    if (parsed && typeof (parsed as { message?: unknown }).message === "string") {
      return (parsed as { message: string }).message;
    }
  } catch {
    return e.body.trim();
  }
  return "";
}

/**
 * 任意异常 → 用户可读文案;null = 无法判定,由调用方兜底。
 * 展示位禁止再直出 e.message / String(e)(红线 R1)。
 */
export function apiErrorMessage(e: unknown): string | null {
  const t = (k: string) => i18n.t(`apiErrors:${k}`);
  if (e instanceof ApiError) {
    const detail = parseDetail(e);
    if (detail) {
      for (const [re, key] of DETAIL_OVERRIDES) {
        if (re.test(detail)) return t(key);
      }
      // 后端中文业务文案(如「余额不足,无法提现」)本身面向用户,直接透传
      if (CJK.test(detail)) return detail;
    }
    return t(statusKind(e.status));
  }
  if (e instanceof TypeError) return t("network");
  if (e instanceof Error) {
    if (e.name === "AbortError") return t("network");
    if (/fetch|network|timeout|ERR_CONNECTION/i.test(e.message)) return t("network");
  }
  return null;
}
