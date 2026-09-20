/**
 * SystemWhitelistEditor — UI for viewing and editing the system command whitelist.
 *
 * Accessed from an admin panel. Shows all configured allowed commands with their
 * flags, subcommands, and limits. Changes are saved via the /api/commands PATCH/PUT
 * endpoints.
 */
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Save, Plus, X, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import type { SystemCommandWhitelist, SystemCommandConfig } from "@/lib/types/api";

interface EditableCommand {
  name: string;
  maxArgs: number;
  allowedFlags: string[];
  allowedSubcommands: string[] | null;
  description: string;
  _new?: boolean;
}

const EMPTY_COMMAND: EditableCommand = {
  name: "",
  maxArgs: 10,
  allowedFlags: [],
  allowedSubcommands: null,
  description: "",
  _new: true,
};

export function SystemWhitelistEditor() {
  const { t } = useTranslation("miscUi");
  const [commands, setCommands] = useState<EditableCommand[]>([]);
  const [dangerousCommands, setDangerousCommands] = useState<string[]>([]);
  const [dangerousPatterns, setDangerousPatterns] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newFlagInput, setNewFlagInput] = useState<Record<string, string>>({});
  const [newSubcmdInput, setNewSubcmdInput] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/commands");
      if (!res.ok) throw new Error();
      const data: SystemCommandWhitelist = await res.json();

      const cmds: EditableCommand[] = Object.entries(data.allowedCommands).map(([name, cfg]) => ({
        name,
        maxArgs: cfg.maxArgs,
        allowedFlags: cfg.allowedFlags,
        allowedSubcommands: cfg.allowedSubcommands,
        description: cfg.description,
      }));
      setCommands(cmds);
      setDangerousCommands(data.dangerousCommands);
      setDangerousPatterns(data.dangerousPatterns);
    } catch {
      toast.error(t("admin.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const saveAll = async () => {
    setSaving(true);
    try {
      const allowedCommands: Record<string, SystemCommandConfig> = {};
      for (const cmd of commands) {
        if (!cmd.name.trim()) continue;
        allowedCommands[cmd.name] = {
          maxArgs: cmd.maxArgs,
          allowedFlags: cmd.allowedFlags,
          allowedSubcommands: cmd.allowedSubcommands,
          description: cmd.description,
        };
      }

      const res = await fetch("/api/commands", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: 1,
          allowedCommands,
          dangerousCommands,
          dangerousPatterns,
        }),
      });

      if (!res.ok) throw new Error();
      toast.success(t("admin.saved"));
      load();
    } catch {
      toast.error(t("admin.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const addCommand = () => {
    setCommands((prev) => [...prev, { ...EMPTY_COMMAND }]);
  };

  const removeCommand = (name: string) => {
    setCommands((prev) => prev.filter((c) => c.name !== name));
  };

  const updateCommand = (name: string, patch: Partial<EditableCommand>) => {
    setCommands((prev) => prev.map((c) => (c.name === name ? { ...c, ...patch } : c)));
  };

  const addFlag = (cmdName: string, flag: string) => {
    const trimmed = flag.trim();
    if (!trimmed) return;
    setCommands((prev) =>
      prev.map((c) =>
        c.name === cmdName && !c.allowedFlags.includes(trimmed)
          ? { ...c, allowedFlags: [...c.allowedFlags, trimmed] }
          : c,
      ),
    );
    setNewFlagInput((prev) => ({ ...prev, [cmdName]: "" }));
  };

  const removeFlag = (cmdName: string, flag: string) => {
    setCommands((prev) =>
      prev.map((c) =>
        c.name === cmdName ? { ...c, allowedFlags: c.allowedFlags.filter((f) => f !== flag) } : c,
      ),
    );
  };

  const addSubcmd = (cmdName: string, subcmd: string) => {
    const trimmed = subcmd.trim();
    if (!trimmed) return;
    setCommands((prev) =>
      prev.map((c) =>
        c.name === cmdName
          ? {
              ...c,
              allowedSubcommands: c.allowedSubcommands
                ? [...c.allowedSubcommands, trimmed]
                : [trimmed],
            }
          : c,
      ),
    );
    setNewSubcmdInput((prev) => ({ ...prev, [cmdName]: "" }));
  };

  const removeSubcmd = (cmdName: string, subcmd: string) => {
    setCommands((prev) =>
      prev.map((c) =>
        c.name === cmdName && c.allowedSubcommands
          ? { ...c, allowedSubcommands: c.allowedSubcommands.filter((s) => s !== subcmd) }
          : c,
      ),
    );
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium">{t("admin.title")}</h2>
          <p className="text-[11px] text-muted-foreground">{t("admin.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={load} className="h-7">
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" onClick={saveAll} className="h-7" disabled={saving}>
            <Save className="w-3 h-3 mr-1" />
            {saving ? t("admin.saving") : t("admin.saveAll")}
          </Button>
        </div>
      </div>

      {/* Command Cards */}
      <div className="space-y-3">
        {commands.map((cmd) => (
          <div key={cmd.name || "new"} className="rounded-lg border border-border/60 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Input
                className="h-7 w-40 text-xs font-mono"
                value={cmd.name}
                onChange={(e) => updateCommand(cmd.name, { name: e.target.value })}
                placeholder={t("admin.cmdNamePlaceholder")}
              />
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Label className="text-xs">maxArgs</Label>
                <Input
                  type="number"
                  min={0}
                  className="h-7 w-16 text-xs"
                  value={cmd.maxArgs}
                  onChange={(e) =>
                    updateCommand(cmd.name, {
                      maxArgs: Number(e.target.value),
                    })
                  }
                />
              </div>
              <Input
                className="h-7 flex-1 text-xs"
                value={cmd.description}
                onChange={(e) => updateCommand(cmd.name, { description: e.target.value })}
                placeholder={t("admin.descriptionPlaceholder")}
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-destructive"
                onClick={() => removeCommand(cmd.name)}
              >
                <Trash2 className="w-3 h-3" />
              </Button>
            </div>

            {/* Flags */}
            <div className="flex flex-wrap gap-1 items-center">
              <span className="text-[11px] text-muted-foreground w-16">allowedFlags</span>
              {cmd.allowedFlags.map((f) => (
                <span
                  key={f}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted text-xs font-mono"
                >
                  {f}
                  <button
                    onClick={() => removeFlag(cmd.name, f)}
                    className="hover:text-destructive"
                    type="button"
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              ))}
              <Input
                className="h-6 w-24 text-xs font-mono"
                value={newFlagInput[cmd.name] ?? ""}
                onChange={(e) =>
                  setNewFlagInput((prev) => ({
                    ...prev,
                    [cmd.name]: e.target.value,
                  }))
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addFlag(cmd.name, newFlagInput[cmd.name] ?? "");
                  }
                }}
                placeholder={t("admin.addFlagPlaceholder")}
              />
            </div>

            {/* Subcommands */}
            {cmd.name === "git" && (
              <div className="flex flex-wrap gap-1 items-center">
                <span className="text-[11px] text-muted-foreground w-16">subcommands</span>
                {(cmd.allowedSubcommands ?? []).map((s) => (
                  <span
                    key={s}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-muted text-xs font-mono"
                  >
                    {s}
                    <button
                      onClick={() => removeSubcmd(cmd.name, s)}
                      className="hover:text-destructive"
                      type="button"
                    >
                      <X className="w-2.5 h-2.5" />
                    </button>
                  </span>
                ))}
                <Input
                  className="h-6 w-24 text-xs font-mono"
                  value={newSubcmdInput[cmd.name] ?? ""}
                  onChange={(e) =>
                    setNewSubcmdInput((prev) => ({
                      ...prev,
                      [cmd.name]: e.target.value,
                    }))
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addSubcmd(cmd.name, newSubcmdInput[cmd.name] ?? "");
                    }
                  }}
                  placeholder={t("admin.addSubcmdPlaceholder")}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      <Button size="sm" variant="outline" onClick={addCommand} className="h-7">
        <Plus className="w-3 h-3 mr-1" /> {t("admin.addCommand")}
      </Button>

      {/* Dangerous Commands */}
      <div className="rounded-lg border border-border/60 p-3 space-y-2">
        <div className="text-xs font-medium text-destructive">{t("admin.dangerousCommands")}</div>
        <div className="flex flex-wrap gap-1">
          {dangerousCommands.map((cmd) => (
            <span
              key={cmd}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-destructive/10 text-xs font-mono text-destructive"
            >
              {cmd}
              <button
                onClick={() => setDangerousCommands((prev) => prev.filter((c) => c !== cmd))}
                className="hover:text-destructive"
                type="button"
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
