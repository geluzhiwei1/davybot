import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Info, Github, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

export function AboutTab() {
  const { t } = useTranslation("userUi");
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Info className="h-4 w-4" /> {t("about.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm">{t("about.version")}</span>
            <Badge variant="outline" className="text-[11px]">
              v0.2.0-beta
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">{t("about.build")}</span>
            <span className="text-sm text-muted-foreground">2024.04.23</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">{t("about.frontend")}</span>
            <span className="text-sm text-muted-foreground">React + TanStack Router</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">{t("about.desktop")}</span>
            <span className="text-sm text-muted-foreground">Tauri 2.x</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">{t("about.uiComponents")}</span>
            <span className="text-sm text-muted-foreground">shadcn/ui</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4 space-y-2">
          <div className="flex items-center gap-2 text-sm cursor-pointer hover:text-primary">
            <Github className="h-4 w-4" /> {t("about.sourceRepo")}
          </div>
          <div className="flex items-center gap-2 text-sm cursor-pointer hover:text-primary">
            <FileText className="h-4 w-4" /> {t("about.license")}
          </div>
        </CardContent>
      </Card>

      <p className="text-center text-xs text-muted-foreground">Copyright (c) 2025 格律至微</p>
    </div>
  );
}
