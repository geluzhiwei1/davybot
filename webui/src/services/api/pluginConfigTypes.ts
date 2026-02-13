/**
 * 插件配置 API 类型定义
 */

// ============================================================================
// 请求/响应模型
// ============================================================================

export interface PluginConfigField {
  name: string;
  type: string;
  description?: string;
  default?: any;
  required?: boolean;
  enum?: Array<{ value: any; label: string }>;
  minimum?: number;
  maximum?: number;
  pattern?: string;
  format?: string;
  hint?: string;
  unit?: string;
  rows?: number;
  placeholder?: string;
  activeText?: string;
  inactiveText?: string;
  disabled?: boolean;
}

export interface PluginConfigManifest {
  schema_version: string;
  schema_type: string;
  title?: string;
  description: string;
  properties: PluginConfigField[];
  required: string[];
}

// ============================================================================
// API 请求模型
// ============================================================================

export interface GetPluginSchemaRequest {
  plugin_id: string;
}

export interface GetPluginConfigRequest {
  plugin_id: string;
}

export interface UpdatePluginConfigRequest {
  plugin_id: string;
  config: Record<string, any>;
}

export interface ResetPluginConfigRequest {
  plugin_id: string;
}

// ============================================================================
// API 响应模型
// ============================================================================

export interface PluginConfigResponse {
  success: boolean;
  schema?: Record<string, any>;
  config: Record<string, any>;
  form_config?: {
    title?: string;
    description?: string;
    submitLabel?: string;
    resetLabel?: string;
  };
  message?: string;
}

export interface PluginListResponse {
  success: boolean;
  plugins: Record<string, {
    manifest: Record<string, any>;
    schema: Record<string, any>;
    config: Record<string, any>;
    form_config?: Record<string, any>;
  }>;
}
