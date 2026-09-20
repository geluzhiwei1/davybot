import { useTheme } from "@/hooks/use-theme";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Sun, Moon, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

const themeOptions = [
  {
    id: "light" as const,
    icon: Sun,
    labelKey: "theme.light",
    color: "bg-yellow-100 text-yellow-700",
  },
  {
    id: "dark" as const,
    icon: Moon,
    labelKey: "theme.dark",
    color: "bg-indigo-100 text-indigo-700",
  },
  {
    id: "system" as const,
    icon: Monitor,
    labelKey: "theme.system",
    color: "bg-gray-100 text-gray-700",
  },
] as const;

export function ThemeSettings() {
  const { mode, activeThemeId, switchCount, lastSwitchedAt, setMode } = useTheme();
  const { t, i18n } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{t("theme.settings")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {themeOptions.map((opt) => {
            const Icon = opt.icon;
            const isActive = mode === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-colors",
                  isActive
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/50",
                )}
              >
                <Icon
                  className={cn("h-6 w-6", isActive ? "text-primary" : "text-muted-foreground")}
                />
                <span className="text-sm font-medium">{t(opt.labelKey)}</span>
                {isActive && (
                  <Badge variant="default" className="text-xs">
                    {t("common.enabled")}
                  </Badge>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {t("theme.switchCount")}: {switchCount}
          </span>
          {lastSwitchedAt && (
            <span>
              {t("theme.lastSwitched")}:{" "}
              {new Date(lastSwitchedAt).toLocaleString(i18n.language === "zh" ? "zh-CN" : "en-US")}
            </span>
          )}
        </div>

        <div className="text-xs text-muted-foreground">
          {t("settings.appearance")}:{" "}
          {activeThemeId === "dark" ? t("theme.dark") : t("theme.light")}
        </div>
      </CardContent>
    </Card>
  );
}
