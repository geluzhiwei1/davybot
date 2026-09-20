import type { ErrorContentBlock } from "@/lib/types";
import { AlertTriangle } from "lucide-react";

interface Props {
  block: ErrorContentBlock;
}

function formatDetails(details: unknown): string {
  if (typeof details === "string") return details;
  return JSON.stringify(details, null, 2);
}

export function ErrorContent({ block }: Props) {
  return (
    <div className="rounded-lg bg-red-500/5 border border-red-500/30 px-3 py-2.5 my-1">
      <div className="flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-sm text-red-600 font-medium">{block.message}</p>
          {block.details != null ? (
            <pre className="mt-1 text-[11px] text-red-500/80 bg-red-500/5 rounded p-2 overflow-x-auto font-mono max-h-32 overflow-y-auto">
              {formatDetails(block.details)}
            </pre>
          ) : null}
        </div>
      </div>
    </div>
  );
}
