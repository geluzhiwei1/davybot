/**
 * MemoryList - Table/list view of memories.
 */
import { dateLocale } from "@/lib/date-locale";
import { useTranslation } from "react-i18next";
import { useMemoryStore } from "@/lib/memory-store";
import { MemoryType } from "@/lib/types/memory";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Check, X, Edit2, Trash2 } from "lucide-react";

const MEMORY_TYPE_LABEL_KEYS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "type.fact",
  [MemoryType.PREFERENCE]: "type.preference",
  [MemoryType.PROCEDURE]: "type.procedure",
  [MemoryType.CONTEXT]: "type.context",
  [MemoryType.STRATEGY]: "type.strategy",
  [MemoryType.EPISODE]: "type.episode",
};

const MEMORY_TYPE_COLORS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "default",
  [MemoryType.PREFERENCE]: "secondary",
  [MemoryType.PROCEDURE]: "outline",
  [MemoryType.CONTEXT]: "destructive",
  [MemoryType.STRATEGY]: "default",
  [MemoryType.EPISODE]: "secondary",
};

export function MemoryList() {
  const { t } = useTranslation("memoryUi");
  const {
    getFilteredMemories,
    setSelectedId,
    selectedId,
    removeMemory,
    setEditingMemory,
    setShowForm,
  } = useMemoryStore();

  const memories = getFilteredMemories();

  const handleEdit = (memoryId: string) => {
    const memory = memories.find((m) => m.id === memoryId);
    if (memory) {
      setEditingMemory(memory);
      setShowForm(true);
    }
  };

  const handleDelete = (memoryId: string) => {
    if (confirm(t("details.deleteConfirm"))) {
      removeMemory(memoryId);
      if (selectedId === memoryId) {
        setSelectedId(null);
      }
    }
  };

  const isValid = (memory: (typeof memories)[0]) => {
    if (!memory.validEnd) return true;
    return new Date(memory.validEnd) > new Date();
  };

  return (
    <ScrollArea className="h-full">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[25%]">{t("list.subject")}</TableHead>
            <TableHead className="w-[15%]">{t("list.predicate")}</TableHead>
            <TableHead className="w-[25%]">{t("list.object")}</TableHead>
            <TableHead className="w-[100px]">{t("list.type")}</TableHead>
            <TableHead className="w-[80px]">{t("list.confidence")}</TableHead>
            <TableHead className="w-[100px]">{t("list.energy")}</TableHead>
            <TableHead className="w-[60px]">{t("list.valid")}</TableHead>
            <TableHead className="w-[120px]">{t("list.createdAt")}</TableHead>
            <TableHead className="w-[100px]">{t("list.actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {memories.length === 0 ? (
            <TableRow>
              <TableCell colSpan={9} className="text-center text-muted-foreground">
                {t("list.empty")}
              </TableCell>
            </TableRow>
          ) : (
            memories.map((memory) => (
              <TableRow
                key={memory.id}
                className={`cursor-pointer ${selectedId === memory.id ? "bg-accent" : ""}`}
                onClick={() => setSelectedId(memory.id)}
              >
                <TableCell className="font-medium">{memory.subject}</TableCell>
                <TableCell>{memory.predicate}</TableCell>
                <TableCell>{memory.object}</TableCell>
                <TableCell>
                  <Badge
                    variant={
                      MEMORY_TYPE_COLORS[memory.memoryType] as
                        "default" | "secondary" | "destructive" | "outline"
                    }
                  >
                    {t(MEMORY_TYPE_LABEL_KEYS[memory.memoryType])}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Progress value={memory.confidence * 100} className="flex-1" />
                    <span className="text-xs text-muted-foreground">
                      {(memory.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Progress value={memory.energy} className="flex-1" />
                </TableCell>
                <TableCell>
                  {isValid(memory) ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : (
                    <X className="h-4 w-4 text-red-500" />
                  )}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {new Date(memory.createdAt).toLocaleDateString(dateLocale())}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleEdit(memory.id);
                      }}
                    >
                      <Edit2 className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(memory.id);
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </ScrollArea>
  );
}
