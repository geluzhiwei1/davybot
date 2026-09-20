/**
 * BlobWindowRenderer — renders backend blob_window structured output.
 * Ported from Vue webui BlobWindowRenderer.vue
 *
 * Data shape: { type: "blob_window", head: [...], tail: [...], omitted: int, hint: str, ... }
 */
import { useTranslation } from "react-i18next";

interface BlobWindowData {
  type: string;
  head?: string[];
  tail?: string[];
  total_lines?: number;
  omitted?: number;
  head_lines?: number;
  tail_lines?: number;
  hint?: string;
}

interface Props {
  data: BlobWindowData;
  startLine?: number;
}

export function BlobWindowRenderer({ data, startLine = 1 }: Props) {
  const { t } = useTranslation("chatUi");
  const head = data.head ?? [];
  const tail = data.tail ?? [];
  const omitted = data.omitted ?? 0;
  const tailStart = startLine + (data.head_lines ?? head.length) + omitted;

  return (
    <div className="font-mono text-[12px] leading-relaxed bg-muted/40 rounded-md p-2 overflow-x-auto">
      {/* Head lines */}
      {head.length > 0 && (
        <div className="space-y-0.5">
          {head.map((line, i) => (
            <div key={`h${i}`} className="flex gap-2">
              <span className="text-muted-foreground/60 min-w-[3rem] text-right select-none shrink-0">
                {startLine + i}
              </span>
              <span className="whitespace-pre-wrap break-all flex-1 min-w-0">{line}</span>
            </div>
          ))}
        </div>
      )}

      {/* Omitted indicator */}
      {omitted > 0 && (
        <div className="text-center py-1.5 text-muted-foreground border-y border-dashed border-border my-1">
          <span className="text-[11px] tracking-wide">
            {t("blobWindow.omitted", { count: omitted })}
          </span>
          {data.hint && <span className="block mt-1 text-[10px] text-primary/80">{data.hint}</span>}
        </div>
      )}

      {/* Tail lines */}
      {tail.length > 0 && (
        <div className="space-y-0.5">
          {tail.map((line, i) => (
            <div key={`t${i}`} className="flex gap-2">
              <span className="text-muted-foreground/60 min-w-[3rem] text-right select-none shrink-0">
                {tailStart + i}
              </span>
              <span className="whitespace-pre-wrap break-all flex-1 min-w-0">{line}</span>
            </div>
          ))}
        </div>
      )}

      {/* Stats */}
      <div className="mt-1.5 text-right">
        <span className="text-[10px] text-muted-foreground">
          {t("blobWindow.showing", {
            shown: (data.head_lines ?? 0) + (data.tail_lines ?? 0),
            total: data.total_lines ?? 0,
          })}
        </span>
      </div>
    </div>
  );
}
