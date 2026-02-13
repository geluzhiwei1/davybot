/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Simplified A2UI Message Processor for Vue
 *
 * This is a lightweight adaptation of the official A2uiMessageProcessor
 * that works directly in Vue applications without requiring the compiled dist.
 *
 * Based on: deps/A2UI/renderers/web_core/src/v0_8/data/model-processor.ts
 */

import type {
  ServerToClientMessage,
  Surface,
  SurfaceID,
  DataMap,
  DataValue,
  BeginRenderingMessage,
  SurfaceUpdateMessage,
  DataModelUpdate,
  DeleteSurfaceMessage,
  ValueMap,
} from './index'

/**
 * Simplified message processor for A2UI
 */
export class A2UIProcessor {
  private surfaces: Map<SurfaceID, Surface> = new Map()

  static readonly DEFAULT_SURFACE_ID = '@default'

  /**
   * Process incoming A2UI messages from the server
   */
  processMessages(messages: ServerToClientMessage[]): void {
    for (const message of messages) {
      if (message.beginRendering) {
        this.handleBeginRendering(message.beginRendering)
      }

      if (message.surfaceUpdate) {
        this.handleSurfaceUpdate(message.surfaceUpdate)
      }

      if (message.dataModelUpdate) {
        this.handleDataModelUpdate(message.dataModelUpdate)
      }

      if (message.deleteSurface) {
        this.handleDeleteSurface(message.deleteSurface)
      }
    }
  }

  /**
   * Get all registered surfaces
   */
  getSurfaces(): ReadonlyMap<SurfaceID, Surface> {
    return this.surfaces
  }

  /**
   * Get a specific surface by ID
   */
  getSurface(surfaceId: SurfaceID): Surface | undefined {
    return this.surfaces.get(surfaceId)
  }

  /**
   * Clear all surfaces
   */
  clearSurfaces(): void {
    this.surfaces.clear()
  }

  /**
   * Delete a specific surface
   */
  deleteSurface(surfaceId: SurfaceID): boolean {
    return this.surfaces.delete(surfaceId)
  }

  private handleBeginRendering(msg: BeginRenderingMessage): void {
    const surface: Surface = {
      rootComponentId: msg.root,
      componentTree: null,
      dataModel: new Map(),
      components: new Map(),
      styles: msg.styles || {},
    }

    this.surfaces.set(msg.surfaceId, surface)
  }

  private handleSurfaceUpdate(msg: SurfaceUpdateMessage): void {
    const surface = this.getOrCreateSurface(msg.surfaceId)
    if (!surface) return

    // Update component registry
    for (const component of msg.components) {
      surface.components.set(component.id, component)
    }

    // Update component tree (simplified - full resolution would be here)
    // For now, we'll let the Vue component handle the tree resolution
  }

  private handleDataModelUpdate(msg: DataModelUpdate): void {
    const surface = this.getOrCreateSurface(msg.surfaceId)
    if (!surface) return

    // Convert ValueMap[] to DataMap
    for (const entry of msg.contents) {
      const value = this.valueMapToDataValue(entry)
      this.setDataAtPath(surface.dataModel, entry.key, value)
    }
  }

  private handleDeleteSurface(msg: DeleteSurfaceMessage): void {
    this.surfaces.delete(msg.surfaceId)
  }

  private getOrCreateSurface(surfaceId: SurfaceID): Surface | undefined {
    if (!this.surfaces.has(surfaceId)) {
      this.surfaces.set(surfaceId, {
        rootComponentId: null,
        componentTree: null,
        dataModel: new Map(),
        components: new Map(),
        styles: {},
      })
    }
    return this.surfaces.get(surfaceId)
  }

  private valueMapToDataValue(map: ValueMap): DataValue {
    // Handle simplified format with direct 'value' key
    if ('value' in map && map.value !== undefined) {
      return map.value as DataValue
    }

    // Handle standard A2UI ValueMap format
    if (map.valueString !== undefined) return map.valueString
    if (map.valueNumber !== undefined) return map.valueNumber
    if (map.valueBoolean !== undefined) return map.valueBoolean
    if (map.valueMap) {
      const obj: Record<string, DataValue> = {}
      for (const item of map.valueMap) {
        obj[item.key] = this.valueMapToDataValue(item)
      }
      return obj
    }
    return null
  }

  private setDataAtPath(dataMap: DataMap, path: string, value: DataValue): void {
    // Simple path implementation (supports "/key" and "/key/subkey")
    if (!path.startsWith('/')) {
      dataMap.set(path, value)
      return
    }

    const keys = path.substring(1).split('/')
    let current = dataMap

    for (let i = 0; i < keys.length - 1; i++) {
      const key = keys[i]
      let next = current.get(key)

      if (!next || typeof next !== 'object' || !(next instanceof Map)) {
        next = new Map()
        current.set(key, next)
      }

      current = next as DataMap
    }

    current.set(keys[keys.length - 1], value)
  }

  /**
   * Get data from a surface's data model using JSON Pointer path
   */
  getData(surfaceId: SurfaceID, path: string): DataValue | null {
    const surface = this.surfaces.get(surfaceId)
    if (!surface) return null

    return this.getDataAtPath(surface.dataModel, path)
  }

  private getDataAtPath(dataMap: DataMap, path: string): DataValue | null {
    if (path === '' || path === '/') {
      return dataMap as unknown
    }

    const keys = path.substring(1).split('/')
    let current: DataValue = dataMap

    for (const key of keys) {
      if (current instanceof Map) {
        current = current.get(key)
      } else if (typeof current === 'object' && current !== null) {
        current = (current as Record<string, unknown>)[key]
      } else {
        return null
      }

      if (current === undefined) {
        return null
      }
    }

    return current
  }
}

// Singleton instance
export const a2uiProcessor = new A2UIProcessor()
