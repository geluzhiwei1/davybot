import type { TextContentBlock } from "@/lib/types";
import { renderMarkdown } from "./markdown";

interface Props {
  block: TextContentBlock;
  isStreaming?: boolean;
}

export function TextContent({ block, isStreaming }: Props) {
  return (
    <div className="space-y-1 text-sm">
      {renderMarkdown(block.text)}
      {isStreaming && (
        <span className="inline-block w-1.5 h-4 bg-brand animate-pulse rounded-sm ml-0.5 align-text-bottom" />
      )}
    </div>
  );
}
