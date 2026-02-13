/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Plugin types
 */

export interface PluginInfo {
  id: string
  name: string
  version: string
  type: PluginType
  description: string
  author: string
  activated: boolean
  enabled: boolean
}

export type PluginType = 'channel' | 'tool' | 'service' | 'memory'

export interface PluginSettings {
  enabled: boolean
  settings: Record<string, unknown>
}

export interface PluginStatistics {
  total_plugins: number
  activated_plugins: number
  by_type: Record<string, number>
  discovery_paths: string[]
}

export interface PluginConfigSchema {
  type: string
  properties: Record<string, PluginPropertySchema>
  required?: string[]
}

export interface PluginPropertySchema {
  type: string
  default?: unknown
  description?: string
  enum?: unknown[]
  format?: string
  pattern?: string
  minimum?: number
  maximum?: number
  min_length?: number
  max_length?: number
}
