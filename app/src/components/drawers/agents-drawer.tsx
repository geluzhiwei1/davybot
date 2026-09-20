/**
 * AgentsDrawer — AI agent/mode management.
 * Lists predefined + custom agents with create/edit/delete/enable-disable controls.
 */
import { useState, useEffect, useMemo } from "react";
import {
  Bot,
  Plus,
  Pencil,
  Trash2,
  Save,
  Scale,
  Gavel,
  FileText,
  Shield,
  Search,
  Book,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { AppDrawer } from "./app-drawer";
import { toExperts } from "@/lib/experts";
import { useMarketTeamsStore } from "@/lib/market-teams-store";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAgentCustomStore, type CustomAgent } from "@/lib/agent-custom-store";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

const HUE_PRESETS = [0, 30, 60, 120, 180, 240, 270, 310, 340];
const ICON_OPTIONS = [
  "Bot",
  "Scale",
  "Gavel",
  "FileText",
  "Shield",
  "Search",
  "Book",
  "Globe",
] as const;

const ICON_MAP: Record<string, LucideIcon> = {
  Bot,
  Scale,
  Gavel,
  FileText,
  Shield,
  Search,
  Book,
  Globe,
};

const emptyForm: Omit<CustomAgent, "id"> = {
  name: "",
  enName: "",
  description: "",
  instructions: "",
  hue: 320,
  icon: "Bot",
  enabled: true,
};

export function AgentsDrawer() {
  const { t } = useTranslation("drawersUi");
  const {
    agents: customAgents,
    disabledDefaultIds,
    addAgent,
    updateAgent,
    deleteAgent,
    toggleDefaultAgent,
  } = useAgentCustomStore();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CustomAgent | null>(null);
  const [form, setForm] = useState<Omit<CustomAgent, "id">>(emptyForm);

  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm);
    setDialogOpen(true);
  };

  const openEdit = (agent: CustomAgent) => {
    setEditing(agent);
    setForm({
      name: agent.name,
      enName: agent.enName ?? "",
      description: agent.description,
      instructions: agent.instructions ?? "",
      hue: agent.hue,
      icon: agent.icon,
      enabled: agent.enabled,
    });
    setDialogOpen(true);
  };

  const handleSave = () => {
    if (!form.name.trim()) {
      toast.error(t("agents.toast.nameRequired"));
      return;
    }
    if (editing) {
      updateAgent(editing.id, form);
      toast.success(t("agents.toast.updated", { name: form.name }));
    } else {
      addAgent(form);
      toast.success(t("agents.toast.created", { name: form.name }));
    }
    setDialogOpen(false);
  };

  const handleDelete = (agent: CustomAgent) => {
    if (confirm(t("agents.confirm.delete", { name: agent.name }))) {
      deleteAgent(agent.id);
      toast.success(t("agents.toast.deleted", { name: agent.name }));
    }
  };

  // Market teams → experts
  const marketTeams = useMarketTeamsStore((s) => s.teams);
  const fetchTeams = useMarketTeamsStore((s) => s.fetchTeams);
  const allExperts = useMemo(() => toExperts(marketTeams), [marketTeams]);
  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  // Merge predefined + custom
  interface MergedAgent {
    id: string;
    name: string;
    emoji?: string;
    enName?: string;
    description: string;
    instructions?: string;
    hue: number;
    icon?: LucideIcon;
    enabled: boolean;
    isCustom: boolean;
  }

  const predefinedAgents: MergedAgent[] = allExperts
    .filter((e) => !disabledDefaultIds.includes(e.id))
    .map((e) => ({
      id: e.id,
      name: e.name,
      emoji: e.icon,
      description: e.description,
      hue: getCategoryHue(e.category),
      enabled: e.enabled,
      isCustom: false,
    }));

  const customList: MergedAgent[] = customAgents.map((a) => ({
    ...a,
    icon: ICON_MAP[a.icon] ?? Bot,
    isCustom: true,
  }));

  const allAgents = [...predefinedAgents, ...customList];

  return (
    <AppDrawer
      id="agents"
      title={t("agents.drawer.title")}
      description={t("agents.drawer.description")}
      icon={Bot}
      badge={t("agents.drawer.badge", { count: allAgents.length })}
      width="w-full sm:w-[520px] sm:max-w-[580px]"
    >
      <div className="flex flex-col h-full">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border/60">
          <span className="text-xs text-muted-foreground">
            {t("agents.toolbar.stats", {
              predefined: predefinedAgents.length,
              predefinedTotal: allExperts.length,
              custom: customAgents.filter((a) => a.enabled).length,
              customTotal: customAgents.length,
            })}
          </span>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={openAdd}>
            <Plus className="w-3 h-3 mr-1" /> {t("agents.toolbar.new")}
          </Button>
        </div>

        {/* Agent list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-2">
          {allAgents.map((agent) => (
            <div
              key={agent.id}
              className={`flex items-start gap-3 px-3 py-3 rounded-lg border transition ${
                agent.enabled
                  ? "border-border/60 hover:border-brand/30 hover:bg-brand/5 cursor-pointer"
                  : "border-border/30 opacity-50 bg-muted/20"
              }`}
            >
              <ExpertIcon
                emoji={agent.emoji}
                hue={agent.hue}
                icon={agent.icon}
                size="sm"
                className="!w-9 !h-9 shrink-0 mt-0.5"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{agent.name}</span>
                  {agent.enName && (
                    <span className="text-[10px] text-muted-foreground">{agent.enName}</span>
                  )}
                  {agent.isCustom ? (
                    <Badge variant="outline" className="text-[10px] bg-brand/5 text-brand">
                      {t("agents.badge.custom")}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px]">
                      {t("agents.badge.builtin")}
                    </Badge>
                  )}
                  {!agent.enabled && (
                    <Badge variant="outline" className="text-[10px] text-muted-foreground">
                      {t("agents.badge.disabled")}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                  {agent.description}
                </p>
                {agent.instructions && (
                  <p className="text-[11px] text-brand/70 mt-0.5 line-clamp-1 italic">
                    {t("agents.list.instructions", { instructions: agent.instructions })}
                  </p>
                )}
              </div>

              {/* Controls */}
              <div className="flex items-center gap-0.5 shrink-0">
                {agent.isCustom ? (
                  <>
                    <Switch
                      checked={agent.enabled}
                      onCheckedChange={() => updateAgent(agent.id, { enabled: !agent.enabled })}
                      className="scale-75"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      onClick={() => openEdit(agent as unknown as CustomAgent)}
                      title={t("agents.action.edit")}
                    >
                      <Pencil className="w-3 h-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      onClick={() => handleDelete(agent as unknown as CustomAgent)}
                      title={t("agents.action.delete")}
                    >
                      <Trash2 className="w-3 h-3 text-destructive" />
                    </Button>
                  </>
                ) : (
                  <Switch
                    checked={agent.enabled}
                    onCheckedChange={() => toggleDefaultAgent(agent.id)}
                    className="scale-75"
                    title={agent.enabled ? t("agents.action.disable") : t("agents.action.enable")}
                  />
                )}
              </div>
            </div>
          ))}

          {allAgents.length === 0 && (
            <div className="text-center py-12 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
              {t("agents.list.empty")}
            </div>
          )}
        </div>

        {/* Create/Edit Dialog */}
        <AgentDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          form={form}
          setForm={setForm}
          onSave={handleSave}
          isEdit={!!editing}
        />
      </div>
    </AppDrawer>
  );
}

// ── Agent Create/Edit Dialog ──────────────────────────────────────────

function AgentDialog({
  open,
  onOpenChange,
  form,
  setForm,
  onSave,
  isEdit,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  form: Omit<CustomAgent, "id">;
  setForm: (f: Omit<CustomAgent, "id">) => void;
  onSave: () => void;
  isEdit: boolean;
}) {
  const { t } = useTranslation("drawersUi");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {isEdit ? t("agents.dialog.editTitle") : t("agents.dialog.addTitle")}
          </DialogTitle>
          <DialogDescription className="text-xs">
            {t("agents.dialog.description")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {/* Name + English name */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("agents.form.name")}</Label>
              <Input
                placeholder={t("agents.form.namePlaceholder")}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("agents.form.enName")}</Label>
              <Input
                placeholder={t("agents.form.enNamePlaceholder")}
                value={form.enName ?? ""}
                onChange={(e) => setForm({ ...form, enName: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t("agents.form.description")}</Label>
            <Textarea
              placeholder={t("agents.form.descriptionPlaceholder")}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="h-16 text-xs resize-none"
            />
          </div>

          {/* Instructions */}
          <div className="space-y-1.5">
            <Label className="text-xs">
              {t("agents.form.instructions")}{" "}
              <span className="text-[10px] text-muted-foreground">
                {t("agents.form.instructionsHint")}
              </span>
            </Label>
            <Textarea
              placeholder={t("agents.form.instructionsPlaceholder")}
              value={form.instructions ?? ""}
              onChange={(e) => setForm({ ...form, instructions: e.target.value || undefined })}
              className="h-20 text-xs resize-none"
            />
          </div>

          <Separator />

          {/* Icon + Color */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("agents.form.icon")}</Label>
              <div className="flex flex-wrap gap-1">
                {ICON_OPTIONS.map((icon) => (
                  <button
                    key={icon}
                    onClick={() => setForm({ ...form, icon })}
                    className={`w-8 h-8 rounded flex items-center justify-center text-xs transition ${
                      form.icon === icon
                        ? "bg-brand/20 text-brand ring-1 ring-brand"
                        : "bg-muted/30 hover:bg-muted/60"
                    }`}
                    title={icon}
                  >
                    <ExpertIcon
                      hue={form.hue}
                      icon={ICON_MAP[icon]}
                      size="sm"
                      className="!w-5 !h-5"
                    />
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("agents.form.hue")}</Label>
              <div className="flex flex-wrap gap-1">
                {HUE_PRESETS.map((h) => (
                  <button
                    key={h}
                    onClick={() => setForm({ ...form, hue: h })}
                    className={`w-6 h-6 rounded-full transition ${
                      form.hue === h
                        ? "ring-2 ring-brand ring-offset-1"
                        : "opacity-60 hover:opacity-90"
                    }`}
                    style={{ backgroundColor: `hsl(${h}, 60%, 55%)` }}
                    title={`H:${h}`}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Enable switch */}
          <div className="flex items-center gap-2">
            <Switch
              checked={form.enabled}
              onCheckedChange={(v) => setForm({ ...form, enabled: v })}
            />
            <Label className="text-xs">{t("agents.form.enable")}</Label>
          </div>
        </div>
        <DialogFooter>
          <Button size="sm" className="h-7 text-xs" onClick={onSave}>
            <Save className="w-3 h-3 mr-1" />
            {isEdit ? t("agents.dialog.saveChanges") : t("agents.dialog.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
