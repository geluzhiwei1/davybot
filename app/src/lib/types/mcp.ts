/**
 * MCP (Model Context Protocol) type definitions — migrated from legalbot/webui/src/types/mcp.ts
 */

export interface MCPServer {
  name: string;
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  timeout?: number;
  disabled?: boolean;
}

export interface MCPServerStatus {
  name: string;
  connected: boolean;
  toolsCount?: number;
  resourcesCount?: number;
  error?: string;
}

export interface MCPTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
  serverName: string;
}

export interface MCPResource {
  uri: string;
  name: string;
  description?: string;
  mimeType?: string;
  serverName: string;
}
