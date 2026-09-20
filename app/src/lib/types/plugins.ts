/**
 * Plugin type definitions — migrated from legalbot/webui/src/types/plugins.ts
 */

export type PluginType = "channel" | "tool" | "service" | "memory";

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  type: PluginType;
  description: string;
  author: string;
  activated: boolean;
  enabled: boolean;
}

export interface PluginSettings {
  enabled: boolean;
  settings: Record<string, unknown>;
}

export interface PluginConfigSchema {
  type: string;
  properties: Record<string, PluginPropertySchema>;
  required?: string[];
}

export interface PluginPropertySchema {
  type: string;
  default?: unknown;
  description?: string;
  enum?: unknown[];
  format?: string;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  min_length?: number;
  max_length?: number;
}

export interface PluginActionParams {
  pluginId: string;
  action: "enable" | "disable" | "activate" | "deactivate" | "reload";
}
