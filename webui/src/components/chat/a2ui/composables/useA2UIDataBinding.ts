/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Data Binding Composable
 *
 * Handles JSON Pointer-based data binding for A2UI components
 */

/**
 * Simple JSON Pointer implementation
 * RFC 6901: https://datatracker.ietf.org/doc/html/rfc6901
 */
class JSONPointer {
  /**
   * Get value at JSON Pointer path
   */
  static get(obj: unknown, pointer: string): unknown {
    if (!pointer || pointer === '/') {
      return obj
    }

    const tokens = this.parse(pointer)
    let current = obj

    for (const token of tokens) {
      if (current == null) {
        return undefined
      }

      // Handle array indices
      if (Array.isArray(current)) {
        const index = parseInt(token, 10)
        if (isNaN(index)) {
          return undefined
        }
        current = current[index]
      } else {
        current = current[token]
      }
    }

    return current
  }

  /**
   * Set value at JSON Pointer path
   */
  static set(obj: unknown, pointer: string, value: unknown): void {
    if (!pointer || pointer === '/') {
      throw new Error('Cannot set root object')
    }

    const tokens = this.parse(pointer)
    const lastToken = tokens.pop()!

    if (tokens.length === 0) {
      // Setting top-level property
      obj[lastToken] = value
      return
    }

    let current = obj

    // Navigate to parent
    for (const token of tokens) {
      if (current[token] == null) {
        // Create intermediate object/array
        const nextToken = tokens[tokens.indexOf(token) + 1]
        const isNextArrayIndex = !isNaN(parseInt(nextToken || '', 10))
        current[token] = isNextArrayIndex ? [] : {}
      }
      current = current[token]
    }

    // Set value
    current[lastToken] = value
  }

  /**
   * Parse JSON Pointer into tokens
   */
  private static parse(pointer: string): string[] {
    if (!pointer.startsWith('/')) {
      throw new Error(`Invalid JSON Pointer: ${pointer}`)
    }

    // Split by '/' and unescape (~1 for /, ~0 for ~)
    return pointer
      .slice(1)
      .split('/')
      .map(token => token.replace(/~1/g, '/').replace(/~0/g, '~'))
  }
}

/**
 * A2UI Data Binding Composable
 */
export function useA2UIDataBinding(
  dataModel: Record<string, unknown>
) {
  /**
   * Resolve data binding path to value
   */
  const resolveBinding = (pointer: string): unknown => {
    try {
      return JSONPointer.get(dataModel, pointer)
    } catch (error) {
      console.error('[A2UI] Failed to resolve binding:', pointer, error)
      return undefined
    }
  }

  /**
   * Update data model at path
   */
  const updateBinding = (pointer: string, value: unknown): void => {
    try {
      JSONPointer.set(dataModel, pointer, value)
    } catch (error) {
      console.error('[A2UI] Failed to update binding:', pointer, error)
    }
  }

  /**
   * Check if path exists in data model
   */
  const hasBinding = (pointer: string): boolean => {
    return resolveBinding(pointer) !== undefined
  }

  return {
    resolveBinding,
    updateBinding,
    hasBinding,
  }
}

/**
 * Parse StringValue (A2UI's data binding or literal value)
 */
export function parseStringValue(
  value: unknown,
  dataModel: Record<string, unknown>
): unknown {
  if (!value) return ''

  // If it's a literal value
  if (value.literalString !== undefined) return value.literalString
  if (value.literalNumber !== undefined) return value.literalNumber
  if (value.literalBoolean !== undefined) return value.literalBoolean

  // If it's a data binding path
  if (value.path) {
    return JSONPointer.get(dataModel, value.path)
  }

  // Fallback
  return value
}
