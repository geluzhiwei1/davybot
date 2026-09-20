/**
 * format-time — B3 / 域 8.2 时间格式统一(第 3 批)。
 *
 * 规则(PRD 09-frontend-design + 可用性升级 域 8.2):
 *   - formatClock(iso):        仅时刻,24 小时制 HH:mm(日历/事件/相对时间列)
 *   - formatSmartTime(iso):    当日 HH:mm / 跨日 MM-DD HH:mm / 跨年 YYYY-MM-DD HH:mm
 *                              (列表、日志、流水等"需要判读何时发生"的场景)
 *
 * 统一 hour12: false —— 修复 en-US 下 locale 默认 12h 与既有 hour12:false
 * 混用导致的同屏 AM/PM 不一致(v1.0 走查:约 20 份自建 helper)。
 * 无效/缺失输入返回 "—"(不抛错、不渲染 Invalid Date)。
 */
import { dateLocale } from "./date-locale";

const CLOCK_OPTS: Intl.DateTimeFormatOptions = {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

function toDate(iso: string | Date | null | undefined): Date | null {
  if (!iso) return null;
  const d = iso instanceof Date ? iso : new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

/** 仅时刻,24h HH:mm(无日期判读需求时用) */
export function formatClock(iso: string | Date | null | undefined): string {
  const d = toDate(iso);
  if (!d) return "—";
  return d.toLocaleTimeString(dateLocale(), CLOCK_OPTS);
}

/** 智能时间:当日 HH:mm / 跨日 MM-DD HH:mm / 跨年含年(域 8.2 规则) */
export function formatSmartTime(iso: string | Date | null | undefined): string {
  const d = toDate(iso);
  if (!d) return "—";
  const now = new Date();
  const locale = dateLocale();
  const clock = d.toLocaleTimeString(locale, CLOCK_OPTS);
  if (d.toDateString() === now.toDateString()) return clock;
  const md = d.toLocaleDateString(locale, { month: "2-digit", day: "2-digit" });
  if (d.getFullYear() === now.getFullYear()) return `${md} ${clock}`;
  const ymd = d.toLocaleDateString(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return `${ymd} ${clock}`;
}
