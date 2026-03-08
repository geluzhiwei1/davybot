/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Data Binding Unit Tests
 */

import { describe, it, expect } from 'vitest'
import { useA2UIDataBinding, parseStringValue } from '@/components/chat/a2ui/composables/useA2UIDataBinding'

describe('useA2UIDataBinding', () => {
  describe('resolveBinding', () => {
    it('should resolve top-level paths', () => {
      const dataModel = {
        username: 'john_doe',
        email: 'john@example.com'
      }

      const { resolveBinding } = useA2UIDataBinding(dataModel)

      expect(resolveBinding('/username')).toBe('john_doe')
      expect(resolveBinding('/email')).toBe('john@example.com')
    })

    it('should resolve nested paths', () => {
      const dataModel = {
        user: {
          profile: {
            name: 'John Doe',
            age: 30
          }
        }
      }

      const { resolveBinding } = useA2UIDataBinding(dataModel)

      expect(resolveBinding('/user/profile/name')).toBe('John Doe')
      expect(resolveBinding('/user/profile/age')).toBe(30)
    })

    it('should resolve array indices', () => {
      const dataModel = {
        users: [
          { name: 'Alice', age: 25 },
          { name: 'Bob', age: 30 }
        ]
      }

      const { resolveBinding } = useA2UIDataBinding(dataModel)

      expect(resolveBinding('/users/0/name')).toBe('Alice')
      expect(resolveBinding('/users/1/age')).toBe(30)
    })

    it('should return undefined for non-existent paths', () => {
      const dataModel = { username: 'john' }

      const { resolveBinding } = useA2UIDataBinding(dataModel)

      expect(resolveBinding('/nonexistent')).toBeUndefined()
      expect(resolveBinding('/user/profile/name')).toBeUndefined()
    })

    it('should handle root path', () => {
      const dataModel = { username: 'john' }

      const { resolveBinding } = useA2UIDataBinding(dataModel)

      expect(resolveBinding('/')).toEqual(dataModel)
      expect(resolveBinding('')).toEqual(dataModel)
    })
  })

  describe('updateBinding', () => {
    it('should update top-level values', () => {
      const dataModel = { username: 'john', email: 'john@example.com' }

      const { updateBinding, resolveBinding } = useA2UIDataBinding(dataModel)

      updateBinding('/username', 'jane')

      expect(resolveBinding('/username')).toBe('jane')
      expect(dataModel.username).toBe('jane')
    })

    it('should update nested values', () => {
      const dataModel = {
        user: {
          profile: {
            name: 'John Doe'
          }
        }
      }

      const { updateBinding, resolveBinding } = useA2UIDataBinding(dataModel)

      updateBinding('/user/profile/name', 'Jane Doe')

      expect(resolveBinding('/user/profile/name')).toBe('Jane Doe')
    })

    it('should update array elements', () => {
      const dataModel = {
        users: ['Alice', 'Bob', 'Charlie']
      }

      const { updateBinding, resolveBinding } = useA2UIDataBinding(dataModel)

      updateBinding('/users/1', 'Robert')

      expect(resolveBinding('/users/1')).toBe('Robert')
      expect(dataModel.users[1]).toBe('Robert')
    })

    it('should create intermediate paths if needed', () => {
      const dataModel = {}

      const { updateBinding, resolveBinding } = useA2UIDataBinding(dataModel)

      updateBinding('/user/profile/name', 'John')

      expect(resolveBinding('/user/profile/name')).toBe('John')
      expect(dataModel.user.profile.name).toBe('John')
    })
  })

  describe('hasBinding', () => {
    it('should return true for existing paths', () => {
      const dataModel = { username: 'john' }

      const { hasBinding } = useA2UIDataBinding(dataModel)

      expect(hasBinding('/username')).toBe(true)
    })

    it('should return false for non-existent paths', () => {
      const dataModel = { username: 'john' }

      const { hasBinding } = useA2UIDataBinding(dataModel)

      expect(hasBinding('/email')).toBe(false)
      expect(hasBinding('/user/profile')).toBe(false)
    })
  })
})

describe('parseStringValue', () => {
  it('should return literal string values', () => {
    const dataModel = { username: 'john' }

    const result = parseStringValue({ literalString: 'Hello World' }, dataModel)

    expect(result).toBe('Hello World')
  })

  it('should return literal number values', () => {
    const dataModel = {}

    const result = parseStringValue({ literalNumber: 42 }, dataModel)

    expect(result).toBe(42)
  })

  it('should return literal boolean values', () => {
    const dataModel = {}

    const result = parseStringValue({ literalBoolean: true }, dataModel)

    expect(result).toBe(true)
  })

  it('should resolve data binding paths', () => {
    const dataModel = {
      user: {
        name: 'John Doe'
      }
    }

    const result = parseStringValue({ path: '/user/name' }, dataModel)

    expect(result).toBe('John Doe')
  })

  it('should return empty string for undefined values', () => {
    const result = parseStringValue(null, {})

    expect(result).toBe('')
  })
})
