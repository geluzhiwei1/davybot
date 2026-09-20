/**
 * AppDrawer — reusable side panel wrapper built on shadcn Sheet.
 * Provides consistent header, width, and animation for all app drawers.
 */
import { type LucideIcon } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";

export type DrawerId =
  "agents" | "llm" | "scheduled" | "workspace-settings" | "user-settings" | "evolution";

interface Props {
  id: DrawerId;
  title: string;
  description?: string;
  icon?: LucideIcon;
  badge?: string;
  width?: string; // Tailwind width class, default full-width on mobile, "sm:w-[480px] sm:max-w-[540px]"
  side?: "left" | "right";
  children: React.ReactNode;
}

export function AppDrawer({
  id,
  title,
  description,
  icon: Icon,
  badge,
  width = "w-full sm:w-[480px] sm:max-w-[540px]",
  side = "right",
  children,
}: Props) {
  const activeDrawer = useStore((s) => s.activeDrawer);
  const setActiveDrawer = useStore((s) => s.setActiveDrawer);
  const open = activeDrawer === id;

  return (
    <Sheet open={open} onOpenChange={(o) => !o && setActiveDrawer(null)}>
      <SheetContent side={side} className={cn(width, "p-0 flex flex-col")}>
        <SheetHeader className="px-6 py-4 border-b border-border/60">
          <SheetTitle className="flex items-center gap-2">
            {Icon && <Icon className="w-4 h-4 text-brand" />}
            {title}
            {badge && (
              <Badge variant="secondary" className="text-[10px] ml-1">
                {badge}
              </Badge>
            )}
          </SheetTitle>
          {description && <SheetDescription className="text-xs">{description}</SheetDescription>}
        </SheetHeader>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
