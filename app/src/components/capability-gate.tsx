/**
 * CapabilityGate — 路由页能力门 (多模式统一方案 §L4)
 *
 * 直达隐藏路由时渲染显式空态「该功能在当前模式({mode})不可用」,
 * 而不是 404 空转。仅做展示层拦截, 后端守卫才是权威。
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";
import { isSectionVisible, type SectionKey } from "@/lib/caps";
import { useCaps } from "@/lib/stores/runtime-store";

export function CapabilityGate({ section, children }: { section: SectionKey; children: ReactNode }) {
  const { t } = useTranslation("commonUi");
  const { caps, mode } = useCaps();

  if (!isSectionVisible(section, caps)) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <EmptyState
          title={t("caps.unavailable", { mode: mode ?? "unknown" })}
          hint={t("caps.unavailableHint")}
        />
      </div>
    );
  }
  return <>{children}</>;
}
