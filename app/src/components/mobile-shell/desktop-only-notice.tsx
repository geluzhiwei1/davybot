/**
 * 方案 Phase 3.6:P2 桌面专属路由的移动端降级引导页。
 *
 * 用于流程设计器(@xyflow 画布拖拽)、创作工场(重编辑器 + 三栏)等
 * 重生产力场景 —— 移动端渲染统一引导页而非不可用的残骸(方案 §2.2
 * desktop-only 分级)。配合 useIsMobile 懒初始化,首帧即正确分流、
 * 无闪屏;重依赖(lute/vditor 等)为动态引入,不渲染编辑器即不加载。
 */
import { MonitorSmartphone } from "lucide-react";
import { useTranslation } from "react-i18next";

export function DesktopOnlyNotice() {
  const { t } = useTranslation("miscUi");
  return (
    <div className="flex h-full min-h-[60dvh] flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/50">
        <MonitorSmartphone className="h-6 w-6 text-muted-foreground" />
      </div>
      <h2 className="text-base font-semibold">{t("desktopOnly.title")}</h2>
      <p className="max-w-xs text-xs leading-relaxed text-muted-foreground">
        {t("desktopOnly.desc")}
      </p>
    </div>
  );
}
