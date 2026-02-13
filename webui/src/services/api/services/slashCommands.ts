/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Slash Commands API Service
 *
 * Provides methods to interact with slash commands API endpoints
 */

import { httpClient } from '../http';

// ============================================================================
// Type Definitions
// ============================================================================

export interface SlashCommand {
  name: string;
  description: string | null;
  argument_hint: string | null;
  mode: string | null;
  source: 'workspace' | 'user' | 'builtin';
  path: string | null;
}

export interface ListCommandsResponse {
  success: boolean;
  total: number;
  commands: SlashCommand[];
  workspace?: string;
  reload?: boolean;
}

export interface GetCommandResponse {
  success: boolean;
  command: SlashCommand & { content: string };
}

export interface ReloadCommandsResponse {
  success: boolean;
  message: string;
  total: number;
  workspace?: string;
}

export interface ExecuteCommandResponse {
  success: boolean;
  result: {
    command: string;
    status: string;
    description?: string;
    mode?: string;
    source?: string;
    content?: string;
    formatted?: string;
    message?: string;
    available_commands?: string[];
    hint?: string;
  };
}

// ============================================================================
// API Service Class
// ============================================================================

export class SlashCommandsApiService {
  private readonly basePath = '/tools/commands';

  /**
   * List all available slash commands
   *
   * @param options - Optional parameters
   * @param options.workspace - Optional workspace path for workspace-specific commands
   * @param options.reload - Force reload commands from disk
   * @returns Promise with list of commands
   */
  async listCommands(options?: {
    workspace?: string;
    reload?: boolean;
  }): Promise<ListCommandsResponse> {
    const params = new URLSearchParams();
    if (options?.workspace) {
      params.append('workspace', options.workspace);
    }
    if (options?.reload) {
      params.append('reload', 'true');
    }

    const queryString = params.toString();
    const url = queryString ? `${this.basePath}?${queryString}` : this.basePath;

    return httpClient.get<ListCommandsResponse>(url);
  }

  /**
   * Get a specific slash command by name
   *
   * @param commandName - Name of the command (without / prefix)
   * @param options - Optional parameters
   * @param options.workspace - Optional workspace path
   * @returns Promise with command details including content
   */
  async getCommand(
    commandName: string,
    options?: { workspace?: string }
  ): Promise<GetCommandResponse> {
    const params = new URLSearchParams();
    if (options?.workspace) {
      params.append('workspace', options.workspace);
    }

    const queryString = params.toString();
    const url = queryString
      ? `${this.basePath}/${commandName}?${queryString}`
      : `${this.basePath}/${commandName}`;

    return httpClient.get<GetCommandResponse>(url);
  }

  /**
   * Reload slash commands from disk
   *
   * Useful after adding/modifying command files without restarting the server.
   *
   * @param options - Optional parameters
   * @param options.workspace - Optional workspace path
   * @returns Promise with reload status
   */
  async reloadCommands(options?: {
    workspace?: string;
  }): Promise<ReloadCommandsResponse> {
    const params = new URLSearchParams();
    if (options?.workspace) {
      params.append('workspace', options.workspace);
    }

    const queryString = params.toString();
    const url = queryString
      ? `${this.basePath}/reload?${queryString}`
      : `${this.basePath}/reload`;

    return httpClient.post<ReloadCommandsResponse>(url);
  }

  /**
   * Execute a slash command and return its content
   *
   * This is a convenience endpoint for testing commands without going through
   * the agent/tool execution flow.
   *
   * @param command - Command name (with or without / prefix)
   * @param options - Optional parameters
   * @param options.args - Optional command arguments
   * @param options.workspace - Optional workspace path
   * @returns Promise with command execution result
   */
  async executeCommand(
    command: string,
    options?: {
      args?: string;
      workspace?: string;
    }
  ): Promise<ExecuteCommandResponse> {
    const params = new URLSearchParams();
    if (options?.workspace) {
      params.append('workspace', options.workspace);
    }
    if (options?.args !== undefined) {
      params.append('args', options.args);
    }

    const queryString = params.toString();
    const url = queryString
      ? `${this.basePath}/execute?${queryString}`
      : `${this.basePath}/execute`;

    return httpClient.post<ExecuteCommandResponse>(url, { command });
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

export const slashCommandsApi = new SlashCommandsApiService();

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * List all available slash commands
 */
export async function listSlashCommands(options?: {
  workspace?: string;
  reload?: boolean;
}): Promise<ListCommandsResponse> {
  return slashCommandsApi.listCommands(options);
}

/**
 * Get a specific slash command by name
 */
export async function getSlashCommand(
  commandName: string,
  options?: { workspace?: string }
): Promise<GetCommandResponse> {
  return slashCommandsApi.getCommand(commandName, options);
}

/**
 * Reload slash commands from disk
 */
export async function reloadSlashCommands(options?: {
  workspace?: string;
}): Promise<ReloadCommandsResponse> {
  return slashCommandsApi.reloadCommands(options);
}

/**
 * Execute a slash command
 */
export async function executeSlashCommand(
  command: string,
  options?: {
    args?: string;
    workspace?: string;
  }
): Promise<ExecuteCommandResponse> {
  return slashCommandsApi.executeCommand(command, options);
}
