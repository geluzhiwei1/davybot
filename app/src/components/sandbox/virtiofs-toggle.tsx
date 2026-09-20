/**
 * VirtiofsToggle — virtiofs 开关 + 本地部署检测提示 (§14.3)
 * 状态归属: 父组件
 */
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

interface VirtiofsToggleProps {
  value: boolean;
  onChange: (v: boolean) => void;
  available?: boolean;
  deploymentMode?: "local" | "saas";
}

export function VirtiofsToggle({
  value,
  onChange,
  available = true,
  deploymentMode,
}: VirtiofsToggleProps) {
  const { t } = useTranslation("sandbox");
  const isLocal = deploymentMode === "local";

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <Switch
          id="virtiofs"
          checked={value}
          onCheckedChange={onChange}
          disabled={!available}
          aria-describedby="virtiofs-desc"
        />
        <Label htmlFor="virtiofs" className="cursor-pointer">
          {t("virtiofs.label")}
        </Label>
      </div>

      {!available && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>{t("virtiofs.unavailable")}</AlertDescription>
        </Alert>
      )}

      {available && isLocal && (
        <p id="virtiofs-desc" className="text-sm text-muted-foreground">
          {t("virtiofs.localNote")}
        </p>
      )}

      {available && !isLocal && (
        <p id="virtiofs-desc" className="text-sm text-muted-foreground">
          {t("virtiofs.cloudNote")}
        </p>
      )}
    </div>
  );
}
