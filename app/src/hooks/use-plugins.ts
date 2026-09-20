import { useState, useCallback } from "react";
import type { PluginInfo } from "@/lib/types/plugins";
import i18n from "@/lib/i18n";

/** Demo plugins — resolved at call time so language switches take effect. */
function buildDemoPlugins(): PluginInfo[] {
  const t = (key: string) => i18n.t(key, { ns: "hooksUi" });
  return [
    {
      id: "p1",
      name: "feishu-channel",
      version: "2.1.0",
      type: "channel",
      description: t("plugins.feishuChannel"),
      author: "格律至微",
      activated: true,
      enabled: true,
    },
    {
      id: "p2",
      name: "docx-parser",
      version: "1.0.3",
      type: "tool",
      description: t("plugins.docxParser"),
      author: "格律至微",
      activated: true,
      enabled: true,
    },
    {
      id: "p3",
      name: "redis-memory",
      version: "1.2.0",
      type: "memory",
      description: t("plugins.redisMemory"),
      author: "格律至微",
      activated: false,
      enabled: true,
    },
    {
      id: "p4",
      name: "pdf-extractor",
      version: "0.8.5",
      type: "tool",
      description: t("plugins.pdfExtractor"),
      author: t("plugins.authorCommunity"),
      activated: false,
      enabled: false,
    },
    {
      id: "p5",
      name: "slack-channel",
      version: "1.0.0",
      type: "channel",
      description: t("plugins.slackChannel"),
      author: t("plugins.authorCommunity"),
      activated: true,
      enabled: true,
    },
  ];
}

export function usePlugins() {
  const [plugins] = useState<PluginInfo[]>(buildDemoPlugins);
  const [loading] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginInfo | null>(null);

  const enabledPlugins = plugins.filter((p) => p.enabled);
  const activePlugins = plugins.filter((p) => p.activated);
  const byType = useCallback((type: string) => plugins.filter((p) => p.type === type), [plugins]);

  return {
    plugins,
    enabledPlugins,
    activePlugins,
    byType,
    loading,
    selectedPlugin,
    setSelectedPlugin,
  };
}
