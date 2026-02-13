/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Unified Workspace ID Resolution Utility
 *
 * Eliminates duplicate workspace resolution logic across the codebase
 * Follows fast-fail principle with proper error handling
 */

import { useConnectionStore } from '@/stores/connection'
import { useWorkspaceStore } from '@/stores/workspace'

export class WorkspaceResolutionError extends Error {
  constructor(message: string, public readonly context?: Record<string, unknown>) {
    super(`[WorkspaceResolution] ${message}`)
    this.name = 'WorkspaceResolutionError'
  }
}

/**
 * Resolve workspace ID from message with fallback hierarchy
 *
 * Resolution order:
 * 1. message.workspace_id (explicit)
 * 2. Resolve from message.session_id via connection store
 * 3. Use current workspace from store (if fallbackToCurrent)
 * 4. Throw error (fast fail)
 *
 * @param message - Message containing workspace_id or session_id
 * @param fallbackToCurrent - Allow falling back to current workspace (default: false for fast fail)
 * @returns Resolved workspace ID
 * @throws {WorkspaceResolutionError} If workspace cannot be resolved
 */
export function resolveWorkspaceId(
  message: { workspace_id?: string; session_id?: string },
  fallbackToCurrent = false
): string {
  const connectionStore = useConnectionStore()
  const workspaceStore = useWorkspaceStore()

  // Layer 1: Explicit workspace_id in message
  if (message.workspace_id) {
    if (message.workspace_id.trim() === '') {
      throw new WorkspaceResolutionError(
        'workspace_id cannot be empty string',
        { workspace_id: message.workspace_id }
      )
    }
    return message.workspace_id
  }

  // Layer 2: Resolve from session_id
  if (message.session_id) {
    const resolved = connectionStore.getWorkspaceIdBySession(message.session_id)
    if (resolved) {
      return resolved
    }
  }

  // Layer 3: Fallback to current workspace (if allowed)
  if (fallbackToCurrent) {
    const current = workspaceStore.currentWorkspaceId
    if (current) {
      return current
    }
    // Use 'default' as last resort
    return 'default'
  }

  // Fast fail: Cannot resolve workspace
  throw new WorkspaceResolutionError(
    'Cannot resolve workspace_id from message',
    {
      has_workspace_id: !!message.workspace_id,
      has_session_id: !!message.session_id,
      fallbackToCurrent
    }
  )
}

/**
 * Validate workspace ID format
 * @param workspaceId - Workspace ID to validate
 * @throws {WorkspaceResolutionError} If invalid
 */
export function validateWorkspaceId(workspaceId: string): void {
  if (!workspaceId || typeof workspaceId !== 'string') {
    throw new WorkspaceResolutionError(
      'workspace_id must be a non-empty string',
      { workspaceId }
    )
  }

  if (workspaceId.trim() === '') {
    throw new WorkspaceResolutionError(
      'workspace_id cannot be empty or whitespace only',
      { workspaceId }
    )
  }

  // Optional: Add format validation (e.g., no special characters)
  if (!/^[a-zA-Z0-9_-]+$/.test(workspaceId)) {
    throw new WorkspaceResolutionError(
      'workspace_id contains invalid characters (only alphanumeric, underscore, hyphen allowed)',
      { workspaceId }
    )
  }
}
