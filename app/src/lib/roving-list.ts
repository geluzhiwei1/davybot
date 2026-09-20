import type { KeyboardEvent } from "react";

/**
 * onRovingListKeyDown — 9.2/域 9:列表方向键 + Enter 导航(roving tabindex)。
 *
 * 用法:
 * - 容器:onKeyDown={onRovingListKeyDown}
 * - 行元素:加 data-roving;首行 tabIndex={0}、其余 tabIndex={-1}
 *   (方向键移动时本函数同步改写 tabIndex,保证任意时刻仅一个 Tab 停靠点)
 * - Enter/Space 激活行内 [data-roving-action],退而求其次首个 a[href];
 *   两者皆无则不动作 —— 行内按钮仍由 Tab 依次到达,绝不替用户触发审批等敏感操作。
 * - 焦点位于行内控件(输入框/按钮)时不劫持按键,交还原生行为。
 */
export function onRovingListKeyDown(e: KeyboardEvent<HTMLElement>) {
  const keys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "];
  if (!keys.includes(e.key)) return;
  const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-roving]"));
  if (items.length === 0) return;
  const active = document.activeElement as HTMLElement | null;
  const idx = active ? items.indexOf(active) : -1;
  if (idx < 0) return; // 焦点在行内控件或容器本身 —— 不劫持

  const focus = (next: number) => {
    const el = items[Math.min(items.length - 1, Math.max(0, next))];
    if (!el) return;
    for (const it of items) it.tabIndex = -1;
    el.tabIndex = 0;
    el.focus();
  };

  e.preventDefault();
  if (e.key === "Enter" || e.key === " ") {
    const target =
      active!.querySelector<HTMLElement>("[data-roving-action]") ??
      active!.querySelector<HTMLElement>("a[href]");
    target?.click();
    return;
  }
  if (e.key === "Home") return focus(0);
  if (e.key === "End") return focus(items.length - 1);
  const delta = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 1;
  focus(idx + delta);
}
