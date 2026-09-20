/**
 * AgentDegradedBanner — displays a warning when agent capabilities are degraded.
 * Shows persistent warning banner when memory or other subsystems failed to initialize.
 */
import { AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgentStore } from "@/lib/agent-store";
import { useTranslation } from "react-i18next";

interface Props {
  workspaceId: string;
}

export function AgentDegradedBanner({ workspaceId }: Props) {
  const degraded = useAgentStore((s) => s.workspaceDegradedFeatures[workspaceId]);
  const clearDegraded = useAgentStore((s) => s.clearDegradedFeatures);
  const { t } = useTranslation("commonUi");

  if (!degraded || Object.keys(degraded).length === 0) return null;

  return (
    <div className="flex items-start gap-2 px-3 py-2 bg-yellow-500/10 border-b border-yellow-500/20 text-yellow-700 dark:text-yellow-400 text-xs">
      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0 space-y-0.5">
        {Object.entries(degraded).map(([feature, info]) => (
          <div key={feature}>
            <span className="font-medium">{featureLabel(feature, t)}</span>
            {": "}
            <span className="opacity-80">{info.impact || info.reason}</span>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-5 w-5 p-0 shrink-0 -mr-0.5 hover:bg-yellow-500/20"
        onClick={() => clearDegraded(workspaceId)}
      >
        <X className="w-3 h-3" />
      </Button>
    </div>
  );
}

function featureLabel(feature: string, t: (key: string) => string): string {
  const keys: Record<string, string> = {
    memory: "degraded.feature.memory",
    knowledge: "degraded.feature.knowledge",
    skills: "degraded.feature.skills",
    mcp: "degraded.feature.mcp",
  };
  return keys[feature] ? t(keys[feature]) : feature;
}
