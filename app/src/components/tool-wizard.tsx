/**
 * ToolWizard — 通用工具向导（2026-09 简化为 2 步）。
 *
 * Step 1 填写需求：所有配置步骤合并为单页分区表单（每步一个分节标题，
 *   一屏可看全、滚动填写，无需逐屏推进）；
 * Step 2 需求单预览：自动生成 markdown 需求单（可编辑），汇总缺失必填项，
 *   并展示流水线启动指令（briefFooter）。
 *
 * 交互原则：步骤可点击自由跳转、未填写也可进入预览查看；
 * 必填校验后移到提交时（预览步汇总缺失项）。
 *
 * 提交后由消费方（ToolPage）创建工作区并把需求单经 setPendingAutoStart
 * 作为开场消息发给会话（驱动 agent 流水线）。
 *
 * 文案沿用 ProductSurveyWizard 先例：硬编码中文，不走 i18n。
 */
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export type ToolWizardFieldType = "input" | "textarea" | "radio";

export interface ToolWizardField {
  key: string;
  label: string;
  /** 必填：提交时校验（不再阻止查看后续步骤） */
  required?: boolean;
  placeholder?: string;
  /** 默认 "input" */
  type?: ToolWizardFieldType;
  /** type === "radio" 时的候选项 */
  options?: string[];
  defaultValue?: string;
}

export interface ToolWizardStep {
  title: string;
  fields: ToolWizardField[];
}

export interface ToolWizardConfig {
  steps: ToolWizardStep[];
  /** 作为任务标题/工作区名的字段 key；缺省取第一步第一个字段 */
  topicKey?: string;
  /** 需求单结尾指令（发给 agent 的开场消息的收尾话术）。缺省用通用话术；
   *  需要驱动 agent 按特定流水线启动时（如原创论文 28 阶段流水线）可覆盖。 */
  briefFooter?: string;
}

export interface ToolWizardSubmitPayload {
  /** 最终（可能被用户编辑过的）markdown 需求单 */
  brief: string;
  /** 主题字段值（无则回退空串），用于任务命名 */
  topic: string;
  /** 原始字段值 */
  values: Record<string, string>;
}

const STEP_TITLES = ["填写需求", "需求单预览"] as const;

/** 分节小标题（合并前的每个配置步骤） */
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold text-foreground/80 border-l-2 border-brand/60 pl-2">
      {children}
    </div>
  );
}

export function ToolWizard({
  config,
  title,
  icon: Icon,
  busy,
  onClose,
  onSubmit,
}: {
  config: ToolWizardConfig;
  /** 工具标题（如「综述写作」），用于头部与需求单标题 */
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  /** 提交中：禁用提交按钮（由消费方创建工作区时置 true） */
  busy?: boolean;
  onClose: () => void;
  onSubmit: (payload: ToolWizardSubmitPayload) => void;
}) {
  const [step, setStep] = useState(1);
  const [brief, setBrief] = useState("");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      config.steps.flatMap((s) => s.fields).map((f) => [f.key, f.defaultValue ?? ""]),
    ),
  );

  const setValue = (key: string, v: string) => setValues((prev) => ({ ...prev, [key]: v }));

  const buildBrief = () => {
    const lines: string[] = [`【${title} · 向导需求单】`];
    config.steps.forEach((s) => {
      const filled = s.fields.filter((f) => (values[f.key] ?? "").trim().length > 0);
      if (filled.length === 0) return;
      lines.push("", `## ${s.title}`);
      filled.forEach((f) => lines.push(`- **${f.label}**：${values[f.key].trim()}`));
    });
    lines.push("", config.briefFooter ?? "请基于以上需求开始，若有不明确之处先向我确认。");
    return lines.join("\n");
  };

  // 进入预览步时生成需求单（仅一次；用户可继续编辑）
  useEffect(() => {
    if (step === 2 && !brief) setBrief(buildBrief());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const topicKey = config.topicKey ?? config.steps[0]?.fields[0]?.key ?? "";
  const topic = (values[topicKey] ?? "").trim();

  /** 提交时才校验的必填项清单（供预览步汇总展示） */
  const missing = useMemo(() => {
    const allFields = config.steps.flatMap((s) =>
      s.fields.filter((f) => f.required).map((f) => ({ step: s.title, label: f.label, key: f.key })),
    );
    return allFields.filter((f) => (values[f.key] ?? "").trim().length === 0);
  }, [config.steps, values]);

  const submit = () => onSubmit({ brief, topic, values });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header + stepper — 可点击自由跳转 */}
      <div className="px-6 py-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="h-8 w-8 md:h-7 md:w-7 p-0" onClick={onClose}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-2 min-w-0">
            {Icon ? (
              <Icon className="w-4 h-4 text-primary shrink-0" />
            ) : (
              <Wand2 className="w-4 h-4 text-primary shrink-0" />
            )}
            <h1 className="text-lg font-bold tracking-tight truncate">向导 · {title}</h1>
          </div>
          <Badge variant="secondary" className="text-[10px] shrink-0">
            Step {step}/2 · {STEP_TITLES[step - 1]}
          </Badge>
        </div>
        <div className="flex items-center gap-1.5 mt-3">
          {STEP_TITLES.map((t, i) => (
            <div key={t} className="flex items-center gap-1.5">
              <button
                type="button"
                disabled={busy}
                onClick={() => setStep(i + 1)}
                className="flex items-center gap-1.5 group disabled:opacity-60"
                title={t}
              >
                <div
                  className={cn(
                    "w-2 h-2 rounded-full transition-colors",
                    i + 1 < step
                      ? "bg-emerald-500"
                      : i + 1 === step
                        ? "bg-primary"
                        : "bg-muted-foreground/30 group-hover:bg-muted-foreground/60",
                  )}
                />
                <span
                  className={cn(
                    "text-[11px] hidden md:inline",
                    i + 1 === step
                      ? "text-foreground font-medium"
                      : "text-muted-foreground group-hover:text-foreground",
                  )}
                >
                  {t}
                </span>
              </button>
              {i < STEP_TITLES.length - 1 && (
                <div className="w-6 h-px bg-muted-foreground/20 mx-0.5 hidden md:block" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6">
        <Card>
          <CardContent className="p-5 space-y-5">
            {/* Step 1 — 所有配置步骤合并为单页分区表单 */}
            {step === 1 &&
              config.steps.map((s) => (
                <div key={s.title} className="space-y-4">
                  <SectionTitle>{s.title}</SectionTitle>
                  {s.fields.map((f) => (
                    <div key={f.key} className="space-y-1.5">
                      <Label className="text-xs">
                        {f.label}
                        {f.required ? " *" : ""}
                      </Label>
                      {(!f.type || f.type === "input") && (
                        <Input
                          value={values[f.key] ?? ""}
                          onChange={(e) => setValue(f.key, e.target.value)}
                          placeholder={f.placeholder}
                          className="text-sm"
                        />
                      )}
                      {f.type === "textarea" && (
                        <Textarea
                          value={values[f.key] ?? ""}
                          onChange={(e) => setValue(f.key, e.target.value)}
                          placeholder={f.placeholder}
                          className="text-xs min-h-[70px]"
                        />
                      )}
                      {f.type === "radio" && (
                        <div className="flex flex-wrap gap-3">
                          {(f.options ?? []).map((o) => (
                            <label key={o} className="flex items-center gap-1.5 text-xs">
                              <input
                                type="radio"
                                checked={values[f.key] === o}
                                onChange={() => setValue(f.key, o)}
                              />
                              {o}
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ))}

            {/* Step 2 — 需求单预览 + 缺失汇总 + 流水线提示 */}
            {step === 2 && (
              <div className="space-y-3">
                {missing.length > 0 && (
                  <div className="rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                    尚未填写的必填项：
                    {missing.map((f) => `${f.label}（${f.step}）`).join("、")}。请返回补充后再提交。
                  </div>
                )}
                <div className="text-xs text-muted-foreground">
                  根据您的选择生成需求单（可编辑）。提交后自动创建工作区并发送给智能体。
                </div>
                <Textarea
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  className="font-mono text-[11px] min-h-[380px]"
                />
                {/* 流水线结合：展示将随需求单下发的流水线启动指令 */}
                {config.briefFooter && (
                  <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 space-y-1">
                    <div className="text-xs font-medium flex items-center gap-1.5">
                      <Wand2 className="w-3.5 h-3.5 text-brand" />
                      提交后将按以下流水线指令启动执行
                    </div>
                    <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono">
                      {config.briefFooter}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-6 py-3 border-t border-border/50">
        <Button
          variant="outline"
          size="sm"
          disabled={step === 1 || busy}
          onClick={() => setStep((s) => s - 1)}
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1" /> 上一步
        </Button>
        {step === 1 ? (
          <Button
            size="sm"
            className="bg-gradient-brand text-brand-foreground"
            disabled={busy}
            onClick={() => setStep(2)}
          >
            预览需求单 <ArrowRight className="w-3.5 h-3.5 ml-1" />
          </Button>
        ) : (
          <Button
            size="sm"
            className="bg-gradient-brand text-brand-foreground"
            disabled={busy || brief.trim().length === 0 || missing.length > 0}
            onClick={submit}
          >
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> 提交并开始
          </Button>
        )}
      </div>
    </div>
  );
}
