/**
 * MountModeSelector — ro/rw radio + 警告 (§14.3)
 * 状态归属: 父组件
 */
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MountMode } from "@/lib/types/sandbox";

interface MountModeSelectorProps {
  value: MountMode;
  onChange: (m: MountMode) => void;
}

export function MountModeSelector({ value, onChange }: MountModeSelectorProps) {
  const { t } = useTranslation("sandbox");
  return (
    <div className="space-y-3">
      <RadioGroup
        value={value}
        onValueChange={(v) => onChange(v as MountMode)}
        className="flex gap-6"
      >
        <div className="flex items-center gap-2">
          <RadioGroupItem value="ro" id="mount-ro" />
          <Label htmlFor="mount-ro" className="cursor-pointer">
            {t("mountMode.ro")}
          </Label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="rw" id="mount-rw" />
          <Label htmlFor="mount-rw" className="cursor-pointer">
            {t("mountMode.rw")}
          </Label>
        </div>
      </RadioGroup>

      {value === "rw" && (
        <Alert variant="destructive">
          <TriangleAlert className="h-4 w-4" />
          <AlertDescription>{t("mountMode.rwWarning")}</AlertDescription>
        </Alert>
      )}
      {value === "ro" && <p className="text-sm text-muted-foreground">{t("mountMode.roNote")}</p>}
    </div>
  );
}
