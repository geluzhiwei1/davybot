import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { STATUS_LABEL } from "@/lib/experts";

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const styles: Record<string, string> = {
    online: "bg-[oklch(0.7_0.18_45)] text-white border-transparent",
    dev: "bg-muted text-muted-foreground border-transparent",
    custom: "bg-[oklch(0.72_0.15_195)] text-[oklch(0.16_0.03_250)] border-transparent",
  };
  return (
    <Badge
      className={cn("font-medium px-2 py-0.5 text-[10px] rounded-md", styles[status], className)}
    >
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}
