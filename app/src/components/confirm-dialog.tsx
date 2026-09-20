/**
 * 通用确认/输入弹窗(可用性标准域 7.1/7.3,红线 R6;拆库方案 §5.2 自 market 下沉核心)。
 * 全模块禁止 window.confirm/alert/prompt,统一走本组件:
 * - 破坏性确认:destructive 变体,「取消」在左,文案由调用方说明具体后果与连带影响(域 7.2)
 * - PromptDialog:替代 window.prompt 的输入弹窗
 *
 * i18n:仅用 marketFlow:actions.cancel —— locale 资源常驻核心(src/lib/locales),
 * 双形态均在场,无倒挂。
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel,
  onConfirm,
  destructive = true,
  busy = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  actionLabel: string;
  onConfirm: () => void | Promise<void>;
  destructive?: boolean;
  busy?: boolean;
}) {
  const { t } = useTranslation("marketFlow");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {description && (
          <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("actions.cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={() => void onConfirm()}
            disabled={busy}
          >
            {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            {actionLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PromptDialog({
  open,
  onOpenChange,
  title,
  label,
  placeholder,
  defaultValue = "",
  actionLabel,
  onConfirm,
  type = "text",
  busy = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  label?: string;
  placeholder?: string;
  defaultValue?: string;
  actionLabel: string;
  onConfirm: (value: string) => void | Promise<void>;
  type?: string;
  busy?: boolean;
}) {
  const { t } = useTranslation("marketFlow");
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    if (open) setValue(defaultValue);
  }, [open, defaultValue]);

  const submit = () => void onConfirm(value);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {label && <div className="text-xs text-muted-foreground">{label}</div>}
        <Input
          autoFocus
          type={type}
          value={value}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("actions.cancel")}
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            {actionLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
