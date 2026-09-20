/**
 * SwipeActionRow — 移动端左滑操作行(移动端可用性方案 · 设计级重构)。
 *
 * 触摸左滑露出右侧操作钮(重命名/删除等);桌面(≥md)渲染为普通行,
 * 行为零变化(操作钮容器 md:hidden,拖拽仅由 touch 事件驱动)。
 * - 意图判定:横向位移 > 纵向才进入拖拽(touch-pan-y 保留纵向滚动);
 * - 互斥:模块级登记,新行展开时收起其它已展开行;
 * - 展开态下点内容 = 仅收起(吞掉 click,防误触行内主操作)。
 */
import { useRef, useState, type ReactNode } from "react";

export interface SwipeAction {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  destructive?: boolean;
}

const ACTION_W = 68;

/** 互斥登记:当前展开行的收起函数。 */
let closeOpenRow: (() => void) | null = null;

export function SwipeActionRow({
  actions,
  children,
}: {
  actions: SwipeAction[];
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [drag, setDrag] = useState(0); // 拖拽中的附加位移(px,≤0)
  const start = useRef<{ x: number; y: number; horizontal: boolean | null } | null>(null);
  const swiped = useRef(false); // 本轮触摸是否构成横向手势(吞合成 click)
  const width = actions.length * ACTION_W;

  const close = () => {
    setOpen(false);
    setDrag(0);
  };
  const closeRef = useRef(close);
  closeRef.current = close;

  const openRow = () => {
    closeOpenRow?.();
    closeOpenRow = () => closeRef.current();
    setOpen(true);
  };

  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    start.current = { x: t.clientX, y: t.clientY, horizontal: null };
  };
  const onTouchMove = (e: React.TouchEvent) => {
    const s = start.current;
    if (!s) return;
    const t = e.touches[0];
    const dx = t.clientX - s.x;
    const dy = t.clientY - s.y;
    if (s.horizontal === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
      s.horizontal = Math.abs(dx) > Math.abs(dy);
    }
    if (s.horizontal) {
      swiped.current = true; // 手势结束后的合成 click 必须吞掉(否则误触行内主操作/折叠头)
      const base = open ? -width : 0;
      setDrag(Math.max(-width, Math.min(0, base + dx)));
    }
  };
  const onTouchEnd = () => {
    const s = start.current;
    if (s?.horizontal) {
      const offset = (open ? -width : 0) + drag;
      if (offset < -width / 3) openRow();
      else close();
    }
    start.current = null;
    setDrag(0);
  };

  return (
    <div className="relative overflow-hidden md:overflow-visible">
      {/* 操作层(仅移动端) */}
      <div className="absolute inset-y-0 right-0 flex md:hidden">
        {actions.map((a) => (
          <button
            key={a.key}
            className={`w-17 flex flex-col items-center justify-center gap-1 text-[10px] font-medium ${
              a.destructive
                ? "bg-destructive text-destructive-foreground"
                : "bg-brand/15 text-brand"
            }`}
            onClick={(e) => {
              e.stopPropagation();
              a.onClick();
              close();
            }}
          >
            <a.icon className="w-4 h-4" />
            {a.label}
          </button>
        ))}
      </div>
      {/* 内容层:不透明底遮住操作层;展开态点击仅收起 */}
      <div
        className="relative transition-transform duration-150 touch-pan-y"
        style={{ transform: `translateX(${(open ? -width : 0) + drag}px)` }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClickCapture={(e) => {
          if (swiped.current) {
            // 横向手势的收尾合成 click:吞掉(不触发行内主操作),不清 open 态
            swiped.current = false;
            e.stopPropagation();
            e.preventDefault();
            return;
          }
          if (open) {
            e.stopPropagation();
            e.preventDefault();
            close();
          }
        }}
      >
        {children}
      </div>
    </div>
  );
}
