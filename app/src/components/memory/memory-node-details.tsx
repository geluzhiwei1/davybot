/**
 * MemoryNodeDetails - Detailed view/edit for a single memory (right-side Sheet).
 */
import { dateLocale } from "@/lib/date-locale";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryStore } from "@/lib/memory-store";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { memoryApi } from "@/lib/memory-service";
import { MemoryType } from "@/lib/types/memory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { Check, X, Edit2, Save, XCircle, Trash2 } from "lucide-react";

const MEMORY_TYPE_LABEL_KEYS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "type.fact",
  [MemoryType.PREFERENCE]: "type.preference",
  [MemoryType.PROCEDURE]: "type.procedure",
  [MemoryType.CONTEXT]: "type.context",
  [MemoryType.STRATEGY]: "type.strategy",
  [MemoryType.EPISODE]: "type.episode",
};

export function MemoryNodeDetails() {
  const { t } = useTranslation("memoryUi");
  const { scope, getSelectedMemory, selectedId, setSelectedId, updateMemory, removeMemory } =
    useMemoryStore();
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const memory = getSelectedMemory();

  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState({
    subject: "",
    predicate: "",
    object: "",
    memoryType: MemoryType.FACT,
    confidence: 0.8,
    energy: 50,
    keywords: [] as string[],
  });

  useEffect(() => {
    if (memory) {
      setEditData({
        subject: memory.subject,
        predicate: memory.predicate,
        object: memory.object,
        memoryType: memory.memoryType,
        confidence: memory.confidence,
        energy: memory.energy,
        keywords: memory.keywords,
      });
      setIsEditing(false);
    }
  }, [memory]);

  const handleClose = () => setSelectedId(null);

  const isValid = !!memory && (!memory.validEnd || new Date(memory.validEnd) > new Date());

  const handleSave = async () => {
    if (!memory) return;
    const apiParams = {
      subject: editData.subject,
      predicate: editData.predicate,
      object: editData.object,
      memory_type: editData.memoryType,
      confidence: editData.confidence,
      energy: editData.energy / 100,
      keywords: editData.keywords,
    };
    try {
      if (scope === "user") {
        await memoryApi.updateUserMemory(memory.id, apiParams);
      } else if (workspaceId) {
        await memoryApi.updateMemory(workspaceId, memory.id, apiParams);
      }
    } catch (err) {
      console.error("Failed to update memory:", err);
    }
    updateMemory(memory.id, editData);
    setIsEditing(false);
  };

  const handleCancel = () => {
    if (memory) {
      setEditData({
        subject: memory.subject,
        predicate: memory.predicate,
        object: memory.object,
        memoryType: memory.memoryType,
        confidence: memory.confidence,
        energy: memory.energy,
        keywords: memory.keywords,
      });
    }
    setIsEditing(false);
  };

  const handleDelete = async () => {
    if (!memory || !confirm(t("details.deleteConfirm"))) return;
    try {
      if (scope === "user") {
        await memoryApi.deleteUserMemory(memory.id);
      } else if (workspaceId) {
        await memoryApi.deleteMemory(workspaceId, memory.id);
      }
    } catch (err) {
      console.error("Failed to delete memory:", err);
    }
    removeMemory(memory.id);
    setSelectedId(null);
  };

  return (
    <Sheet
      open={!!selectedId}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] overflow-y-auto">
        <SheetHeader className="pb-3 pr-8">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-lg">{t("details.title")}</SheetTitle>
            <div className="flex items-center gap-1">
              {isValid ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <X className="h-4 w-4 text-red-500" />
              )}
              {isEditing ? (
                <>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleSave}>
                    <Save className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCancel}>
                    <XCircle className="h-3 w-3" />
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setIsEditing(true)}
                  >
                    <Edit2 className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive"
                    onClick={handleDelete}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </>
              )}
            </div>
          </div>
        </SheetHeader>

        {memory && (
          <div className="space-y-4">
            {/* Triple */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">{t("details.triple")}</Label>
              {isEditing ? (
                <div className="space-y-2">
                  <Input
                    value={editData.subject}
                    onChange={(e) => setEditData({ ...editData, subject: e.target.value })}
                    placeholder={t("details.subjectPlaceholder")}
                  />
                  <Input
                    value={editData.predicate}
                    onChange={(e) => setEditData({ ...editData, predicate: e.target.value })}
                    placeholder={t("details.predicatePlaceholder")}
                  />
                  <Input
                    value={editData.object}
                    onChange={(e) => setEditData({ ...editData, object: e.target.value })}
                    placeholder={t("details.objectPlaceholder")}
                  />
                </div>
              ) : (
                <div className="p-3 bg-muted rounded-md space-y-1">
                  <div className="font-medium">{memory.subject}</div>
                  <div className="text-sm text-muted-foreground">{memory.predicate}</div>
                  <div className="text-sm">{memory.object}</div>
                </div>
              )}
            </div>

            <Separator />

            {/* Type */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">{t("details.memoryType")}</Label>
              {isEditing ? (
                <Select
                  value={editData.memoryType}
                  onValueChange={(value) =>
                    setEditData({ ...editData, memoryType: value as MemoryType })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(MemoryType).map((type) => (
                      <SelectItem key={type} value={type}>
                        {t(MEMORY_TYPE_LABEL_KEYS[type])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Badge>{t(MEMORY_TYPE_LABEL_KEYS[memory.memoryType])}</Badge>
              )}
            </div>

            {/* Confidence */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">
                {t("details.confidence", { value: (editData.confidence * 100).toFixed(0) })}
              </Label>
              {isEditing ? (
                <Slider
                  value={[editData.confidence]}
                  onValueChange={([value]) => setEditData({ ...editData, confidence: value })}
                  min={0}
                  max={1}
                  step={0.05}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary"
                      style={{ width: `${memory.confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-sm">{(memory.confidence * 100).toFixed(0)}%</span>
                </div>
              )}
            </div>

            {/* Energy */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">
                {t("details.energy", { value: editData.energy })}
              </Label>
              {isEditing ? (
                <Slider
                  value={[editData.energy]}
                  onValueChange={([value]) => setEditData({ ...editData, energy: value })}
                  min={0}
                  max={100}
                  step={5}
                />
              ) : (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full bg-primary" style={{ width: `${memory.energy}%` }} />
                  </div>
                  <span className="text-sm">{memory.energy}</span>
                </div>
              )}
            </div>

            <Separator />

            {/* Keywords */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">{t("details.keywords")}</Label>
              <div className="flex flex-wrap gap-1">
                {memory.keywords.map((keyword) => (
                  <Badge key={keyword} variant="outline" className="text-xs">
                    {keyword}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Validity */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">{t("details.validity")}</Label>
              <div className="text-sm space-y-1">
                <div>
                  {t("details.validStart", {
                    date: new Date(memory.validStart).toLocaleDateString(dateLocale()),
                  })}
                </div>
                {memory.validEnd ? (
                  <div>
                    {t("details.validEnd", {
                      date: new Date(memory.validEnd).toLocaleDateString(dateLocale()),
                    })}
                  </div>
                ) : (
                  <div className="text-muted-foreground">{t("details.permanent")}</div>
                )}
              </div>
            </div>

            <Separator />

            {/* Metadata */}
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">{t("details.metadata")}</Label>
              <div className="text-sm space-y-1">
                <div>{t("details.accessCount", { count: memory.accessCount })}</div>
                <div>
                  {t("details.createdAt", {
                    value: new Date(memory.createdAt).toLocaleString(dateLocale()),
                  })}
                </div>
                <div>
                  {t("details.updatedAt", {
                    value: new Date(memory.updatedAt).toLocaleString(dateLocale()),
                  })}
                </div>
              </div>
            </div>

            {/* Source Event */}
            {memory.sourceEventId && (
              <>
                <Separator />
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">
                    {t("details.sourceEvent")}
                  </Label>
                  <div className="text-sm font-mono bg-muted p-2 rounded">
                    {memory.sourceEventId}
                  </div>
                </div>
              </>
            )}

            {/* Custom Metadata */}
            {Object.keys(memory.metadata).length > 0 && (
              <>
                <Separator />
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">{t("details.customData")}</Label>
                  <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-32">
                    {JSON.stringify(memory.metadata, null, 2)}
                  </pre>
                </div>
              </>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
