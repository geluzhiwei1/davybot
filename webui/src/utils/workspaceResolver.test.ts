/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * @file Unit tests for workspaceResolver utility
 * @see workspaceResolver.ts
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  resolveWorkspaceId,
  WorkspaceResolutionError
} from './workspaceResolver'
import { useConnectionStore } from '@/stores/connection'
import { useWorkspaceStore } from '@/stores/workspace'

describe('workspaceResolver', () => {
  beforeEach(() => {
    // Create fresh pinia instance for each test
    const pinia = createPinia()
    setActivePinia(pinia)

    // Clear all mocks
    vi.clearAllMocks()
  })

  describe('resolveWorkspaceId', () => {
    it('should return workspace_id from message when provided', () => {
      const message = { workspace_id: 'test-workspace' }
      const result = resolveWorkspaceId(message, false)
      expect(result).toBe('test-workspace')
    })

    it('should return workspace_id when fallbackToCurrent is true', () => {
      const message = { workspace_id: 'test-workspace' }
      const result = resolveWorkspaceId(message, true)
      expect(result).toBe('test-workspace')
    })

    it('should throw WorkspaceResolutionError for empty string workspace_id', () => {
      const message = { workspace_id: '   ' }
      expect(() => resolveWorkspaceId(message, false))
        .toThrow(WorkspaceResolutionError)
    })

    it('should throw WorkspaceResolutionError with trimmed whitespace workspace_id', () => {
      const message = { workspace_id: '  ' }
      expect(() => resolveWorkspaceId(message, false))
        .toThrow(WorkspaceResolutionError)

      try {
        resolveWorkspaceId(message, false)
      } catch (error) {
        expect(error).toBeInstanceOf(WorkspaceResolutionError)
        expect((error as WorkspaceResolutionError).message).toContain('workspace_id cannot be empty string')
      }
    })

    it('should resolve workspace_id from session_id via connection store', () => {
      const connectionStore = useConnectionStore()

      // Mock connection store to return workspace ID for session
      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue('resolved-workspace')

      const message = { session_id: 'test-session' }
      const result = resolveWorkspaceId(message, false)

      expect(result).toBe('resolved-workspace')
      expect(connectionStore.getWorkspaceIdBySession).toHaveBeenCalledWith('test-session')
    })

    it('should return current workspace_id when fallbackToCurrent is true and no other resolution possible', () => {
      const connectionStore = useConnectionStore()
      const workspaceStore = useWorkspaceStore()

      // Mock connection store to return undefined
      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue(undefined)
      // Mock workspace store to return current workspace
      vi.spyOn(workspaceStore, 'currentWorkspaceId', 'get').mockReturnValue('current-workspace')

      const message = { session_id: 'test-session' }
      const result = resolveWorkspaceId(message, true)

      expect(result).toBe('current-workspace')
    })

    it('should return default workspace when fallbackToCurrent is true and currentWorkspaceId is empty', () => {
      const connectionStore = useConnectionStore()
      const workspaceStore = useWorkspaceStore()

      // Mock stores
      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue(undefined)
      vi.spyOn(workspaceStore, 'currentWorkspaceId', 'get').mockReturnValue('')

      const message = { session_id: 'test-session' }
      const result = resolveWorkspaceId(message, true)

      expect(result).toBe('default')
    })

    it('should throw WorkspaceResolutionError when workspace_id cannot be resolved and fallbackToCurrent is false', () => {
      const connectionStore = useConnectionStore()

      // Mock connection store to return undefined
      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue(undefined)

      const message = { session_id: 'test-session' }

      expect(() => resolveWorkspaceId(message, false))
        .toThrow(WorkspaceResolutionError)
    })

    it('should throw WorkspaceResolutionError with detailed message', () => {
      const connectionStore = useConnectionStore()

      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue(undefined)

      const message = { session_id: 'test-session' }

      try {
        resolveWorkspaceId(message, false)
        expect.fail('Should have thrown WorkspaceResolutionError')
      } catch (error) {
        expect(error).toBeInstanceOf(WorkspaceResolutionError)
        expect((error as WorkspaceResolutionError).message).toContain('Cannot resolve workspace_id')
      }
    })

    it('should throw WorkspaceResolutionError when message is empty object', () => {
      const message = {}

      expect(() => resolveWorkspaceId(message, false))
        .toThrow(WorkspaceResolutionError)
    })

    it('should throw WorkspaceResolutionError when message has neither workspace_id nor session_id', () => {
      const message = { some_other_field: 'value' }

      expect(() => resolveWorkspaceId(message, false))
        .toThrow(WorkspaceResolutionError)
    })

    it('should prioritize workspace_id over session_id', () => {
      const connectionStore = useConnectionStore()

      // Even if connection store has a session mapping, workspace_id should win
      vi.spyOn(connectionStore, 'getWorkspaceIdBySession').mockReturnValue('session-workspace')

      const message = {
        workspace_id: 'direct-workspace',
        session_id: 'test-session'
      }

      const result = resolveWorkspaceId(message, false)
      expect(result).toBe('direct-workspace')
      expect(connectionStore.getWorkspaceIdBySession).not.toHaveBeenCalled()
    })

    it('should handle workspace_id with special characters', () => {
      const message = { workspace_id: 'my-workspace-123_test' }
      const result = resolveWorkspaceId(message, false)
      expect(result).toBe('my-workspace-123_test')
    })

    it('should preserve workspace_id case', () => {
      const message = { workspace_id: 'MyWorkspace' }
      const result = resolveWorkspaceId(message, false)
      expect(result).toBe('MyWorkspace')
    })
  })

  describe('WorkspaceResolutionError', () => {
    it('should create error instance with message', () => {
      const error = new WorkspaceResolutionError('Test error message')
      expect(error.message).toBe('[WorkspaceResolution] Test error message')
    })

    it('should create error instance with message and context', () => {
      const context = { workspaceId: 'test-workspace' }
      const error = new WorkspaceResolutionError('Test error', context)

      expect(error.message).toBe('[WorkspaceResolution] Test error')
      expect(error.context).toEqual(context)
    })

    it('should be instanceof Error', () => {
      const error = new WorkspaceResolutionError('Test')
      expect(error instanceof Error).toBe(true)
    })

    it('should have correct name', () => {
      const error = new WorkspaceResolutionError('Test')
      expect(error.name).toBe('WorkspaceResolutionError')
    })
  })
})
