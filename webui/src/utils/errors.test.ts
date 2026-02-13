/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * @file Unit tests for custom error classes
 * @see errors.ts
 */

import { describe, it, expect } from 'vitest'
import {
  AppError,
  NetworkError,
  WebSocketError,
  WebSocketDispatchError,
  HttpError,
  ValidationError,
  WorkspaceError
} from './errors'
import { WorkspaceResolutionError } from './workspaceResolver'

describe('Custom Error Classes', () => {
  describe('AppError', () => {
    it('should create error instance with message and code', () => {
      const error = new AppError('Test error', 'TEST_CODE')
      expect(error.message).toBe('Test error')
      expect(error.code).toBe('TEST_CODE')
      expect(error.name).toBe('AppError')
    })

    it('should create error instance with context', () => {
      const context = { userId: '123', action: 'test' }
      const error = new AppError('Test error', 'TEST_CODE', context)

      expect(error.context).toEqual(context)
      expect(error.context?.userId).toBe('123')
    })

    it('should be instanceof Error', () => {
      const error = new AppError('Test', 'CODE')
      expect(error instanceof Error).toBe(true)
      expect(error instanceof AppError).toBe(true)
    })

    it('should have stack trace', () => {
      const error = new AppError('Test', 'CODE')
      expect(error.stack).toBeDefined()
      expect(typeof error.stack).toBe('string')
    })
  })

  describe('NetworkError', () => {
    it('should create error with message', () => {
      const error = new NetworkError('Network request failed')
      expect(error.message).toBe('Network request failed')
      expect(error.code).toBe('NETWORK_ERROR')
      expect(error.name).toBe('NetworkError')
    })

    it('should create error with context', () => {
      const context = { url: '/api/test', status: 500 }
      const error = new NetworkError('Network error', context)

      expect(error.context).toEqual(context)
      expect(error.code).toBe('NETWORK_ERROR')
    })

    it('should be instanceof AppError', () => {
      const error = new NetworkError('Test')
      expect(error instanceof AppError).toBe(true)
      expect(error instanceof NetworkError).toBe(true)
    })
  })

  describe('WebSocketError', () => {
    it('should create error with message', () => {
      const error = new WebSocketError('WebSocket connection failed')
      expect(error.message).toBe('WebSocket connection failed')
      expect(error.code).toBe('WEBSOCKET_ERROR')
      expect(error.name).toBe('WebSocketError')
    })

    it('should create error with context', () => {
      const context = { workspaceId: 'test', url: 'ws://localhost' }
      const error = new WebSocketError('Connection failed', context)

      expect(error.context).toEqual(context)
    })

    it('should be instanceof AppError', () => {
      const error = new WebSocketError('Test')
      expect(error instanceof AppError).toBe(true)
      expect(error instanceof WebSocketError).toBe(true)
    })
  })

  describe('WebSocketDispatchError', () => {
    it('should create error with message', () => {
      const error = new WebSocketDispatchError('Message dispatch failed')
      expect(error.message).toBe('Message dispatch failed')
      expect(error.code).toBe('WEBSOCKET_DISPATCH_ERROR')
      expect(error.name).toBe('WebSocketDispatchError')
    })

    it('should add dispatch flag to context', () => {
      const error = new WebSocketDispatchError('Test')
      expect(error.context?.dispatch).toBe(true)
    })

    it('should merge user context with dispatch flag', () => {
      const context = { messageType: 'user_message' }
      const error = new WebSocketDispatchError('Test', context)

      expect(error.context?.dispatch).toBe(true)
      expect(error.context?.messageType).toBe('user_message')
    })

    it('should be instanceof WebSocketError', () => {
      const error = new WebSocketDispatchError('Test')
      expect(error instanceof WebSocketError).toBe(true)
      expect(error instanceof AppError).toBe(true)
    })
  })

  describe('HttpError', () => {
    it('should create error with message and status code', () => {
      const error = new HttpError('HTTP request failed', 404)
      expect(error.message).toBe('HTTP request failed')
      expect(error.code).toBe('HTTP_ERROR')
      expect(error.name).toBe('HttpError')
      expect(error.statusCode).toBe(404)
    })

    it('should create error with context', () => {
      const context = { url: '/api/test' }
      const error = new HttpError('Not found', 404, context)

      expect(error.context?.url).toBe('/api/test')
      expect(error.context?.statusCode).toBe(404)
      expect(error.statusCode).toBe(404)
    })

    it('should be instanceof AppError', () => {
      const error = new HttpError('Test', 500)
      expect(error instanceof AppError).toBe(true)
      expect(error instanceof HttpError).toBe(true)
    })
  })

  describe('ValidationError', () => {
    it('should create error with message', () => {
      const error = new ValidationError('Invalid input')
      expect(error.message).toBe('Invalid input')
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.name).toBe('ValidationError')
    })

    it('should create error with context', () => {
      const context = { field: 'email', value: 'invalid' }
      const error = new ValidationError('Invalid email', context)

      expect(error.context).toEqual(context)
    })

    it('should be instanceof AppError', () => {
      const error = new ValidationError('Test')
      expect(error instanceof AppError).toBe(true)
      expect(error instanceof ValidationError).toBe(true)
    })
  })

  describe('WorkspaceError', () => {
    it('should create error with message', () => {
      const error = new WorkspaceError('Workspace not found')
      expect(error.message).toBe('Workspace not found')
      expect(error.code).toBe('WORKSPACE_ERROR')
      expect(error.name).toBe('WorkspaceError')
    })

    it('should create error with context', () => {
      const context = { workspaceId: 'test-workspace' }
      const error = new WorkspaceError('Not found', context)

      expect(error.context).toEqual(context)
    })

    it('should be instanceof AppError', () => {
      const error = new WorkspaceError('Test')
      expect(error instanceof AppError).toBe(true)
      expect(error instanceof WorkspaceError).toBe(true)
    })
  })

  describe('WorkspaceResolutionError', () => {
    it('should create error with message and auto-prefix', () => {
      const error = new WorkspaceResolutionError('Cannot resolve workspace')
      expect(error.message).toBe('[WorkspaceResolution] Cannot resolve workspace')
      expect(error.name).toBe('WorkspaceResolutionError')
    })

    it('should create error with context', () => {
      const context = { workspaceId: 'test', sessionId: 'abc' }
      const error = new WorkspaceResolutionError('Resolution failed', context)

      expect(error.context).toEqual(context)
    })

    it('should be instanceof Error', () => {
      const error = new WorkspaceResolutionError('Test')
      expect(error instanceof Error).toBe(true)
    })

    it('should not have code property (unlike other errors)', () => {
      const error = new WorkspaceResolutionError('Test')
      expect((error as unknown).code).toBeUndefined()
    })
  })
})
