import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface OAPlaceholderProps {
  title: string;
  subtitle: string;
  description: string;
  icon: LucideIcon;
}

export function OAPlaceholder({ title, subtitle, description, icon: Icon }: OAPlaceholderProps) {
  const { t } = useTranslation("commonUi");
  return (
    <div className="flex-1 flex flex-col">
      <div className="px-6 py-4 border-b border-border/60">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold">{title}</h1>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-warning/15 text-warning border border-warning/30">
            {t("oa.badge")}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
      </div>
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-2xl border border-border/60 bg-card/40 backdrop-blur p-8 text-center shadow-elegant">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-gradient-brand flex items-center justify-center shadow-brand mb-4">
            <Icon className="w-6 h-6 text-[oklch(0.16_0.03_250)]" strokeWidth={2.2} />
          </div>
          <h2 className="text-lg font-semibold mb-2">{t("oa.title")}</h2>
          <p className="text-sm text-muted-foreground leading-relaxed mb-6">{description}</p>
          <div className="flex items-center justify-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/">{t("oa.backHome")}</Link>
            </Button>
            <Button asChild size="sm" className="bg-gradient-brand text-brand-foreground">
              <Link to="/experts">
                <Sparkles className="w-3.5 h-3.5 mr-1" />
                {t("oa.exploreExperts")}
              </Link>
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground/70 mt-6">{t("oa.comingSoon")}</p>
        </div>
      </div>
    </div>
  );
}
