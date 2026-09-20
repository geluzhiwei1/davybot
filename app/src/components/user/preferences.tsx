import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useChatStore } from "@/lib/chat-store";

export function PreferencesTab() {
  const { t } = useTranslation("userUi");
  const [prefs, setPrefs] = useState({
    language: "zh",
    timezone: "Asia/Shanghai",
    theme: "dark",
    autoSave: true,
  });

  // Chat display preferences — store-backed with localStorage persistence
  const compactMode = useChatStore((s) => s.compactMode);
  const setCompactMode = useChatStore((s) => s.setCompactMode);
  const fontSize = useChatStore((s) => s.fontSize);
  const setFontSize = useChatStore((s) => s.setFontSize);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t("prefs.display")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm">{t("prefs.language")}</Label>
            <Select
              value={prefs.language}
              onValueChange={(v) => setPrefs({ ...prefs, language: v })}
            >
              <SelectTrigger className="w-40 h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zh">{t("prefs.langZh")}</SelectItem>
                <SelectItem value="en">English</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">{t("prefs.theme")}</Label>
            <Select value={prefs.theme} onValueChange={(v) => setPrefs({ ...prefs, theme: v })}>
              <SelectTrigger className="w-40 h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="light">{t("prefs.themeLight")}</SelectItem>
                <SelectItem value="dark">{t("prefs.themeDark")}</SelectItem>
                <SelectItem value="auto">{t("prefs.themeAuto")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">{t("prefs.fontSize", { size: fontSize })}</Label>
            <Slider
              value={[fontSize]}
              onValueChange={([v]) => setFontSize(v)}
              min={12}
              max={20}
              step={1}
              className="w-40"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t("prefs.editor")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm">{t("prefs.autoSave")}</Label>
            <Switch
              checked={prefs.autoSave}
              onCheckedChange={(v) => setPrefs({ ...prefs, autoSave: v })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">{t("prefs.compactMode")}</Label>
            <Switch checked={compactMode} onCheckedChange={setCompactMode} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
