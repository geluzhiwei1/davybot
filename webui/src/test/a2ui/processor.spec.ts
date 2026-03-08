/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Processor Unit Tests
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { A2UIProcessor } from '@/a2ui/processor'

describe('A2UIProcessor', () => {
  let processor: A2UIProcessor

  beforeEach(() => {
    processor = new A2UIProcessor()
  })

  describe('processMessages', () => {
    it('should process beginRendering message', () => {
      const messages = [
        {
          beginRendering: {
            surfaceId: 'test-surface',
            root: 'root-component',
            styles: { backgroundColor: '#fff' }
          }
        }
      ]

      processor.processMessages(messages)

      const surfaces = processor.getSurfaces()
      expect(surfaces.has('test-surface')).toBe(true)

      const surface = surfaces.get('test-surface')
      expect(surface?.rootComponentId).toBe('root-component')
      expect(surface?.styles).toEqual({ backgroundColor: '#fff' })
    })

    it('should process surfaceUpdate message', () => {
      const messages = [
        {
          beginRendering: {
            surfaceId: 'test-surface',
            root: 'comp1',
            styles: {}
          }
        },
        {
          surfaceUpdate: {
            surfaceId: 'test-surface',
            components: [
              {
                id: 'comp1',
                component: {
                  type: 'Text',
                  text: 'Hello World'
                }
              },
              {
                id: 'comp2',
                component: {
                  type: 'Button'
                }
              }
            ]
          }
        }
      ]

      processor.processMessages(messages)

      const surface = processor.getSurface('test-surface')
      expect(surface?.components.size).toBe(2)
      expect(surface?.components.has('comp1')).toBe(true)
      expect(surface?.components.has('comp2')).toBe(true)
    })

    it('should process dataModelUpdate message', () => {
      const messages = [
        {
          beginRendering: {
            surfaceId: 'test-surface',
            root: '',
            styles: {}
          }
        },
        {
          dataModelUpdate: {
            surfaceId: 'test-surface',
            contents: [
              { key: 'username', value: 'john_doe' },
              { key: 'email', value: 'john@example.com' },
              { key: 'age', valueNumber: 30 }
            ]
          }
        }
      ]

      processor.processMessages(messages)

      const surface = processor.getSurface('test-surface')
      expect(surface?.dataModel.get('username')).toBe('john_doe')
      expect(surface?.dataModel.get('email')).toBe('john@example.com')
      expect(surface?.dataModel.get('age')).toBe(30)
    })

    it('should process deleteSurface message', () => {
      const messages = [
        {
          beginRendering: {
            surfaceId: 'test-surface',
            root: '',
            styles: {}
          }
        },
        {
          deleteSurface: {
            surfaceId: 'test-surface'
          }
        }
      ]

      processor.processMessages(messages)

      expect(processor.getSurface('test-surface')).toBeUndefined()
    })

    it('should handle multiple messages in one batch', () => {
      const messages = [
        {
          beginRendering: {
            surfaceId: 'surface1',
            root: 'root1',
            styles: {}
          }
        },
        {
          beginRendering: {
            surfaceId: 'surface2',
            root: 'root2',
            styles: {}
          }
        },
        {
          surfaceUpdate: {
            surfaceId: 'surface1',
            components: []
          }
        }
      ]

      processor.processMessages(messages)

      expect(processor.getSurfaces().size).toBe(2)
      expect(processor.getSurface('surface1')).toBeDefined()
      expect(processor.getSurface('surface2')).toBeDefined()
    })
  })

  describe('getData', () => {
    beforeEach(() => {
      processor.processMessages([
        {
          beginRendering: {
            surfaceId: 'test-surface',
            root: '',
            styles: {}
          }
        },
        {
          dataModelUpdate: {
            surfaceId: 'test-surface',
            contents: [
              { key: 'username', value: 'john' },
              { key: 'profile', valueMap: [
                { key: 'name', value: 'John Doe' },
                { key: 'age', valueNumber: 30 }
              ]}
            ]
          }
        }
      ])
    })

    it('should retrieve top-level data', () => {
      const result = processor.getData('test-surface', '/username')
      expect(result).toBe('john')
    })

    it('should retrieve nested data using JSON Pointer', () => {
      const result = processor.getData('test-surface', '/profile/name')
      expect(result).toBe('John Doe')
    })

    it('should return null for non-existent paths', () => {
      const result = processor.getData('test-surface', '/nonexistent')
      expect(result).toBeNull()
    })

    it('should return null for non-existent surfaces', () => {
      const result = processor.getData('invalid-surface', '/username')
      expect(result).toBeNull()
    })
  })

  describe('clearSurfaces', () => {
    it('should remove all surfaces', () => {
      processor.processMessages([
        { beginRendering: { surfaceId: 's1', root: '', styles: {} } },
        { beginRendering: { surfaceId: 's2', root: '', styles: {} } }
      ])

      expect(processor.getSurfaces().size).toBe(2)

      processor.clearSurfaces()

      expect(processor.getSurfaces().size).toBe(0)
    })
  })

  describe('deleteSurface', () => {
    it('should delete specific surface', () => {
      processor.processMessages([
        { beginRendering: { surfaceId: 's1', root: '', styles: {} } },
        { beginRendering: { surfaceId: 's2', root: '', styles: {} } }
      ])

      const deleted = processor.deleteSurface('s1')

      expect(deleted).toBe(true)
      expect(processor.getSurface('s1')).toBeUndefined()
      expect(processor.getSurface('s2')).toBeDefined()
    })

    it('should return false for non-existent surface', () => {
      const deleted = processor.deleteSurface('nonexistent')
      expect(deleted).toBe(false)
    })
  })
})
