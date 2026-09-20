import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Shield, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useState } from "react";

export function SecuritySettingsTab() {
  const { t } = useTranslation("userUi");
  const [settings, setSettings] = useState({
    enableCommandWhitelist: true,
    enableSandbox: false,
    allowShellCommands: false,
    allowBackgroundCommands: false,
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Shield className="h-4 w-4" /> {t("security.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">{t("security.whitelist")}</Label>
              <p className="text-xs text-muted-foreground">{t("security.whitelistDesc")}</p>
            </div>
            <Switch
              checked={settings.enableCommandWhitelist}
              onCheckedChange={(v) => setSettings({ ...settings, enableCommandWhitelist: v })}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">{t("security.sandbox")}</Label>
              <p className="text-xs text-muted-foreground">{t("security.sandboxDesc")}</p>
            </div>
            <Switch
              checked={settings.enableSandbox}
              onCheckedChange={(v) => setSettings({ ...settings, enableSandbox: v })}
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm">{t("security.shell")}</Label>
              <p className="text-xs text-muted-foreground">{t("security.shellDesc")}</p>
            </div>
            <Switch
              checked={settings.allowShellCommands}
              onCheckedChange={(v) => setSettings({ ...settings, allowShellCommands: v })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t("security.sessions")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-2">
              <Monitor className="h-4 w-4" />
              <div>
                <p className="text-sm font-medium">{t("security.currentDevice")}</p>
                <p className="text-xs text-muted-foreground">Chrome / Linux</p>
              </div>
            </div>
            <Badge variant="outline" className="text-[10px]">
              {t("security.active")}
            </Badge>
          </div>
          <Button variant="outline" size="sm" className="w-full h-7 text-xs">
            {t("security.logoutOthers")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
