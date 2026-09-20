/**
 * useSidebarCounts — 聚合各 biz 域注册的 sidebar 徽标计数(核心形态恒为空)。
 *
 * 取数/轮询/窗口聚焦刷新等域内逻辑(如智能律所的 dashboard.stats 汇总)经
 * biz-registry 的 BIZ_SIDEBAR_COUNT_HOOKS 注入;此处只做逐域合并,
 * key 冲突时后注册域覆盖(跨域 key 命名本就带域前缀,正常不冲突)。
 */
import { BIZ_SIDEBAR_COUNT_HOOKS } from "@/lib/biz-registry";

export function useSidebarCounts(): { counts: Record<string, number> } {
  const counts: Record<string, number> = {};
  // BIZ_SIDEBAR_COUNT_HOOKS 为构建期常量数组(长度固定),逐项调用 hook 合法
  for (const entry of BIZ_SIDEBAR_COUNT_HOOKS) {
    Object.assign(counts, entry.useCounts());
  }
  return { counts };
}
