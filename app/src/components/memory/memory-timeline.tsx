/**
 * MemoryTimeline - Timeline view grouped by date.
 */
import { dateLocale } from "@/lib/date-locale";
import { useTranslation } from "react-i18next";
import { useMemoryStore } from "@/lib/memory-store";
import { MemoryType } from "@/lib/types/memory";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const MEMORY_TYPE_LABEL_KEYS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "type.fact",
  [MemoryType.PREFERENCE]: "type.preference",
  [MemoryType.PROCEDURE]: "type.procedure",
  [MemoryType.CONTEXT]: "type.context",
  [MemoryType.STRATEGY]: "type.strategy",
  [MemoryType.EPISODE]: "type.episode",
};

const MEMORY_TYPE_COLORS: Record<MemoryType, "default" | "secondary" | "destructive" | "outline"> =
  {
    [MemoryType.FACT]: "default",
    [MemoryType.PREFERENCE]: "secondary",
    [MemoryType.PROCEDURE]: "outline",
    [MemoryType.CONTEXT]: "destructive",
    [MemoryType.STRATEGY]: "default",
    [MemoryType.EPISODE]: "secondary",
  };

export function MemoryTimeline() {
  const { t } = useTranslation("memoryUi");
  const { getFilteredMemories, setSelectedId, selectedId } = useMemoryStore();

  const memories = getFilteredMemories();

  // Group memories by date
  const groupedMemories = memories.reduce(
    (acc, memory) => {
      const date = new Date(memory.createdAt).toLocaleDateString(dateLocale());
      if (!acc[date]) {
        acc[date] = [];
      }
      acc[date].push(memory);
      return acc;
    },
    {} as Record<string, typeof memories>,
  );

  const sortedDates = Object.keys(groupedMemories).sort(
    (a, b) => new Date(b).getTime() - new Date(a).getTime(),
  );

  return (
    <ScrollArea className="h-full">
      <div className="p-6">
        {sortedDates.length === 0 ? (
          <div className="text-center text-muted-foreground py-12">{t("timeline.empty")}</div>
        ) : (
          <div className="space-y-6">
            {sortedDates.map((date, dateIndex) => (
              <div key={date} className="relative">
                {/* Date header */}
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex items-center justify-center w-12 h-12 rounded-full bg-primary text-primary-foreground font-bold">
                    {new Date(date).getDate()}
                  </div>
                  <div>
                    <div className="font-semibold text-lg">{date}</div>
                    <div className="text-sm text-muted-foreground">
                      {t("timeline.count", { count: groupedMemories[date].length })}
                    </div>
                  </div>
                </div>

                {/* Timeline line */}
                {dateIndex < sortedDates.length - 1 && (
                  <div className="absolute left-[23px] top-16 bottom-[-24px] w-0.5 bg-border" />
                )}

                {/* Memories for this date */}
                <div className="ml-16 space-y-3">
                  {groupedMemories[date]
                    .sort(
                      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
                    )
                    .map((memory) => (
                      <Card
                        key={memory.id}
                        className={`p-4 cursor-pointer transition-colors hover:bg-accent ${
                          selectedId === memory.id ? "border-primary" : ""
                        }`}
                        onClick={() => setSelectedId(memory.id)}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 space-y-2">
                            {/* Triple */}
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-medium">{memory.subject}</span>
                              <span className="text-muted-foreground">{memory.predicate}</span>
                              <span className="text-muted-foreground">{memory.object}</span>
                            </div>

                            {/* Metadata */}
                            <div className="flex items-center gap-3 text-sm">
                              <Badge variant={MEMORY_TYPE_COLORS[memory.memoryType]}>
                                {t(MEMORY_TYPE_LABEL_KEYS[memory.memoryType])}
                              </Badge>
                              <span className="text-muted-foreground">
                                {t("timeline.confidence", {
                                  value: (memory.confidence * 100).toFixed(0),
                                })}
                              </span>
                              <span className="text-muted-foreground">
                                {t("timeline.energy", { value: memory.energy })}
                              </span>
                              {memory.keywords.length > 0 && (
                                <div className="flex items-center gap-1">
                                  <span className="text-muted-foreground">
                                    {t("timeline.keywords")}
                                  </span>
                                  {memory.keywords.slice(0, 3).map((kw) => (
                                    <span
                                      key={kw}
                                      className="px-1.5 py-0.5 bg-muted rounded text-xs"
                                    >
                                      {kw}
                                    </span>
                                  ))}
                                  {memory.keywords.length > 3 && (
                                    <span className="text-muted-foreground text-xs">
                                      +{memory.keywords.length - 3}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Time */}
                          <div className="text-sm text-muted-foreground whitespace-nowrap">
                            {new Date(memory.createdAt).toLocaleTimeString(dateLocale(), {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </div>
                        </div>
                      </Card>
                    ))}
                </div>

                {dateIndex < sortedDates.length - 1 && <Separator className="mt-6" />}
              </div>
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
