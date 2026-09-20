/**
 * MemoryForm - Create/edit memory form.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryStore } from "@/lib/memory-store";
import { useWorkspaceStore } from "@/lib/workspace-store";
import { memoryApi } from "@/lib/memory-service";
import { MemoryType } from "@/lib/types/memory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

const MEMORY_TYPE_LABEL_KEYS: Record<MemoryType, string> = {
  [MemoryType.FACT]: "type.fact",
  [MemoryType.PREFERENCE]: "type.preference",
  [MemoryType.PROCEDURE]: "type.procedure",
  [MemoryType.CONTEXT]: "type.context",
  [MemoryType.STRATEGY]: "type.strategy",
  [MemoryType.EPISODE]: "type.episode",
};

interface FormData {
  subject: string;
  predicate: string;
  object: string;
  memoryType: MemoryType;
  confidence: number;
  energy: number;
  keywords: string;
  validStart?: string;
  validEnd?: string;
}

const defaultFormData: FormData = {
  subject: "",
  predicate: "",
  object: "",
  memoryType: MemoryType.FACT,
  confidence: 0.8,
  energy: 50,
  keywords: "",
  validStart: new Date().toISOString().split("T")[0],
  validEnd: "",
};

export function MemoryForm() {
  const { t } = useTranslation("memoryUi");
  const { scope, showForm, setShowForm, editingMemory, addMemory, updateMemory, setEditingMemory } =
    useMemoryStore();
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  const [formData, setFormData] = useState<FormData>(defaultFormData);
  const [errors, setErrors] = useState<Partial<Record<keyof FormData, string>>>({});
  const [submitting, setSubmitting] = useState(false);

  // Initialize form when editing
  useEffect(() => {
    if (editingMemory) {
      setFormData({
        subject: editingMemory.subject,
        predicate: editingMemory.predicate,
        object: editingMemory.object,
        memoryType: editingMemory.memoryType,
        confidence: editingMemory.confidence,
        energy: editingMemory.energy,
        keywords: editingMemory.keywords.join(", "),
        validStart: editingMemory.validStart.split("T")[0],
        validEnd: editingMemory.validEnd ? editingMemory.validEnd.split("T")[0] : "",
      });
    } else {
      setFormData(defaultFormData);
    }
    setErrors({});
  }, [editingMemory, showForm]);

  const validate = (): boolean => {
    const newErrors: Partial<Record<keyof FormData, string>> = {};

    if (!formData.subject.trim()) {
      newErrors.subject = t("form.error.subject");
    }
    if (!formData.predicate.trim()) {
      newErrors.predicate = t("form.error.predicate");
    }
    if (!formData.object.trim()) {
      newErrors.object = t("form.error.object");
    }
    if (formData.confidence < 0 || formData.confidence > 1) {
      newErrors.confidence = t("form.error.confidence");
    }
    if (formData.energy < 0 || formData.energy > 100) {
      newErrors.energy = t("form.error.energy");
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const keywords = formData.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);

    const apiParams = {
      subject: formData.subject,
      predicate: formData.predicate,
      object: formData.object,
      memory_type: formData.memoryType,
      confidence: formData.confidence,
      energy: formData.energy / 100, // UI 0-100 → API 0.0-1.0
      keywords,
    };

    setSubmitting(true);
    try {
      if (editingMemory) {
        // Update via API
        if (scope === "user") {
          await memoryApi.updateUserMemory(editingMemory.id, apiParams);
        } else if (workspaceId) {
          await memoryApi.updateMemory(workspaceId, editingMemory.id, apiParams);
        }
        // Update local store
        updateMemory(editingMemory.id, {
          subject: formData.subject,
          predicate: formData.predicate,
          object: formData.object,
          memoryType: formData.memoryType,
          confidence: formData.confidence,
          energy: formData.energy,
          keywords,
          validStart: formData.validStart,
          validEnd: formData.validEnd || undefined,
        });
      } else {
        // Create via API
        const res =
          scope === "user"
            ? await memoryApi.createUserMemory(apiParams)
            : workspaceId
              ? await memoryApi.createMemory(workspaceId, apiParams)
              : null;

        const newMemory = {
          id: res?.id || `memory-${Date.now()}`,
          subject: res?.subject || formData.subject,
          predicate: res?.predicate || formData.predicate,
          object: res?.object || formData.object,
          validStart: res?.valid_start || formData.validStart || new Date().toISOString(),
          validEnd: res?.valid_end || formData.validEnd || undefined,
          confidence: res?.confidence ?? formData.confidence,
          energy: res?.energy ?? formData.energy,
          accessCount: res?.access_count ?? 0,
          memoryType: (res?.memory_type as MemoryType) || formData.memoryType,
          keywords: res?.keywords || keywords,
          sourceEventId: res?.source_event_id || undefined,
          metadata: res?.metadata || {},
          createdAt: res?.created_at || new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        addMemory(newMemory);
      }
    } catch (err) {
      console.error("Failed to persist memory:", err);
    } finally {
      setSubmitting(false);
    }

    handleClose();
  };

  const handleClose = () => {
    setShowForm(false);
    setEditingMemory(null);
    setFormData(defaultFormData);
    setErrors({});
  };

  return (
    <Dialog open={showForm} onOpenChange={setShowForm}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{editingMemory ? t("form.editTitle") : t("form.addTitle")}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Subject */}
          <div className="space-y-2">
            <Label htmlFor="subject">
              {t("form.subject")} <span className="text-destructive">*</span>
            </Label>
            <Input
              id="subject"
              value={formData.subject}
              onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
              placeholder={t("form.subjectPlaceholder")}
              className={errors.subject ? "border-destructive" : ""}
            />
            {errors.subject && <span className="text-sm text-destructive">{errors.subject}</span>}
          </div>

          {/* Predicate */}
          <div className="space-y-2">
            <Label htmlFor="predicate">
              {t("form.predicate")} <span className="text-destructive">*</span>
            </Label>
            <Input
              id="predicate"
              value={formData.predicate}
              onChange={(e) => setFormData({ ...formData, predicate: e.target.value })}
              placeholder={t("form.predicatePlaceholder")}
              className={errors.predicate ? "border-destructive" : ""}
            />
            {errors.predicate && (
              <span className="text-sm text-destructive">{errors.predicate}</span>
            )}
          </div>

          {/* Object */}
          <div className="space-y-2">
            <Label htmlFor="object">
              {t("form.object")} <span className="text-destructive">*</span>
            </Label>
            <Input
              id="object"
              value={formData.object}
              onChange={(e) => setFormData({ ...formData, object: e.target.value })}
              placeholder={t("form.objectPlaceholder")}
              className={errors.object ? "border-destructive" : ""}
            />
            {errors.object && <span className="text-sm text-destructive">{errors.object}</span>}
          </div>

          {/* Memory Type */}
          <div className="space-y-2">
            <Label htmlFor="type">{t("form.memoryType")}</Label>
            <Select
              value={formData.memoryType}
              onValueChange={(value) =>
                setFormData({ ...formData, memoryType: value as MemoryType })
              }
            >
              <SelectTrigger id="type">
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
          </div>

          {/* Confidence */}
          <div className="space-y-2">
            <Label htmlFor="confidence">
              {t("form.confidence", { value: (formData.confidence * 100).toFixed(0) })}
            </Label>
            <Slider
              id="confidence"
              value={[formData.confidence]}
              onValueChange={([value]) => setFormData({ ...formData, confidence: value })}
              min={0}
              max={1}
              step={0.05}
            />
          </div>

          {/* Energy */}
          <div className="space-y-2">
            <Label htmlFor="energy">{t("form.energy", { value: formData.energy })}</Label>
            <Slider
              id="energy"
              value={[formData.energy]}
              onValueChange={([value]) => setFormData({ ...formData, energy: value })}
              min={0}
              max={100}
              step={5}
            />
          </div>

          {/* Keywords */}
          <div className="space-y-2">
            <Label htmlFor="keywords">{t("form.keywords")}</Label>
            <Input
              id="keywords"
              value={formData.keywords}
              onChange={(e) => setFormData({ ...formData, keywords: e.target.value })}
              placeholder={t("form.keywordsPlaceholder")}
            />
          </div>

          {/* Valid Start */}
          <div className="space-y-2">
            <Label htmlFor="validStart">{t("form.validStart")}</Label>
            <Input
              id="validStart"
              type="date"
              value={formData.validStart}
              onChange={(e) => setFormData({ ...formData, validStart: e.target.value })}
            />
          </div>

          {/* Valid End */}
          <div className="space-y-2">
            <Label htmlFor="validEnd">{t("form.validEnd")}</Label>
            <Input
              id="validEnd"
              type="date"
              value={formData.validEnd}
              onChange={(e) => setFormData({ ...formData, validEnd: e.target.value })}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("form.submitting") : editingMemory ? t("form.save") : t("form.add")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
