/**
 * 通用空态组件(可用性标准域 5.1/5.2,红线 R5;拆库方案 §5.2 自 market 下沉核心)。
 * 空态必须回答三问:这里是什么(title)/ 为什么是空的(hint)/ 下一步做什么(action 按钮必选其一)。
 */
import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyState({
  title,
  hint,
  action,
  icon,
}: {
  title: string;
  hint?: string;
  action?: { label: string; onClick: () => void };
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12 text-center">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-muted-foreground">
        {icon ?? <Inbox className="h-4 w-4" />}
      </div>
      <div className="text-sm text-foreground">{title}</div>
      {hint && <div className="max-w-md text-xs leading-relaxed text-muted-foreground">{hint}</div>}
      {action && (
        <Button size="sm" variant="outline" className="mt-1" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
