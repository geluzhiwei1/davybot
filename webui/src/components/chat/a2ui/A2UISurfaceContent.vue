/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="a2ui-surface" :class="surfaceClasses">
    <!-- Surface Header -->
    <div v-if="surfaceMetadata?.title" class="a2ui-surface-header">
      <h3 class="a2ui-surface-title">{{ surfaceMetadata.title }}</h3>
      <p v-if="surfaceMetadata.description" class="a2ui-surface-description">
        {{ surfaceMetadata.description }}
      </p>
    </div>

    <!-- Surface Container -->
    <div class="a2ui-surface-container" :style="containerStyle">
      <!-- Loading State -->
      <div v-if="loading" class="a2ui-surface-loading">
        <el-skeleton :rows="3" animated />
      </div>

      <!-- Error State -->
      <el-alert
        v-else-if="error"
        type="error"
        :title="error"
        :closable="false"
        show-icon
      />

      <!-- Empty State -->
      <el-empty
        v-else-if="!rootComponent"
        description="No UI components to display"
      />

      <!-- A2UI Component Tree -->
      <A2UIAdapter
        v-else
        :node="rootComponent"
        :data-model="reactiveDataModel"
        :surface-id="surfaceId"
        @action="handleUserAction"
      />

      <!-- Debug Info (dev only) -->
      <div v-if="isDev && showDebug" class="a2ui-surface-debug">
        <el-collapse>
          <el-collapse-item title="Debug Info" name="debug">
            <div class="debug-section">
              <h4>Surface ID:</h4>
              <code>{{ surfaceId }}</code>

              <h4>Data Model:</h4>
              <pre>{{ JSON.stringify(reactiveDataModel, null, 2) }}</pre>

              <h4>Components:</h4>
              <pre>{{ JSON.stringify(components, null, 2) }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import A2UIAdapter from './A2UIAdapter.vue'
import { a2uiProcessor } from '@/a2ui/processor'
import type { A2UISurfaceContentBlock } from '@/types/websocket'
import type { AnyComponentNode } from '@/a2ui'
import { useConnectionStore } from '@/stores/connection'

const props = defineProps<{
  block: A2UISurfaceContentBlock
}>()

const connectionStore = useConnectionStore()

// State
const loading = ref(true)
const error = ref<string>()
const showDebug = ref(false)
const isDev = computed(() => import.meta.env.DEV)

// Surface data
const surfaceId = computed(() => props.block.surfaceId)
const surfaceMetadata = computed(() => props.block.metadata)

// Data model (reactive)
const reactiveDataModel = computed({
  get: () => props.block.dataModel as Record<string, unknown>,
  set: (value) => {
    // TODO: Update data model via WebSocket
    console.log('[A2UI] Data model updated:', value)
  }
})

// Components
const components = computed(() => props.block.components)

// Root component
const rootComponent = computed<AnyComponentNode | null>(() => {
  const surface = a2uiProcessor.getSurface(surfaceId.value)

  if (surface?.rootComponentId) {
    const component = components.value.find(
      c => c.id === surface.rootComponentId
    )

    if (component) {
      // Convert ComponentInstance to AnyComponentNode
      return convertComponentToNode(component)
    }
  }

  // Fallback: first component
  if (components.value.length > 0) {
    return convertComponentToNode(components.value[0])
  }

  return null
})

// Surface classes
const surfaceClasses = computed(() => {
  return [
    `a2ui-surface-${props.block.surfaceType}`,
    {
      'a2ui-surface-interactive': surfaceMetadata.value?.interactive,
    }
  ]
})

// Container style
const containerStyle = computed(() => {
  const style: Record<string, string> = {}

  if (surfaceMetadata.value?.layout) {
    style.display = surfaceMetadata.value.layout === 'horizontal' ? 'flex' : 'block'
  }

  return style
})

/**
 * Convert ComponentInstance to AnyComponentNode
 * This is a simplified conversion - in production, the A2UI processor
 * would handle this with full resolution
 */
function convertComponentToNode(component: unknown): AnyComponentNode {
  return {
    id: component.id,
    type: component.component?.type || 'Custom',
    weight: component.weight,
    dataContextPath: component.component?.dataContextPath,
    slotName: component.component?.slotName,
    properties: component.component || {},
  }
}

/**
 * Handle user action from A2UI component
 */
function handleUserAction(payload: {
  surfaceId: string
  componentId: string
  actionName: string
  timestamp: string
  context?: Record<string, unknown>
}) {
  console.log('[A2UI] User action:', payload)

  // Send action to backend via WebSocket
  if (connectionStore.isConnected) {
    connectionStore.sendMessage({
      type: 'a2ui_user_action',
      surfaceId: payload.surfaceId,
      componentId: payload.componentId,
      actionName: payload.actionName,
      context: payload.context,
    } as unknown)

    ElMessage.success(`Action sent: ${payload.actionName}`)
  } else {
    ElMessage.error('Not connected to server')
  }
}

// Lifecycle
onMounted(() => {
  // Register surface with processor
  const surface = a2uiProcessor.getSurface(surfaceId.value)

  if (!surface) {
    // Initialize surface
    a2uiProcessor.processMessages([
      {
        beginRendering: {
          surfaceId: surfaceId.value,
          root: components.value[0]?.id || '',
          styles: {},
        },
      },
      {
        surfaceUpdate: {
          surfaceId: surfaceId.value,
          components: components.value,
        },
      },
      {
        dataModelUpdate: {
          surfaceId: surfaceId.value,
          contents: Object.entries(props.block.dataModel).map(([key, value]) => ({
            key,
            value,
          })),
        },
      },
    ])
  }

  loading.value = false
})

// Watch for updates to components or data model
watch(
  () => [props.block.components, props.block.dataModel],
  () => {
    // Update surface with new data
    a2uiProcessor.processMessages([
      {
        surfaceUpdate: {
          surfaceId: surfaceId.value,
          components: props.block.components,
        },
      },
      {
        dataModelUpdate: {
          surfaceId: surfaceId.value,
          contents: Object.entries(props.block.dataModel).map(([key, value]) => ({
            key,
            value,
          })),
        },
      },
    ])
  },
  { deep: true }
)
</script>

<style scoped>
.a2ui-surface {
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
  background-color: var(--el-bg-color);
  margin: 12px 0;
  overflow: hidden;
}

.a2ui-surface-interactive {
  cursor: pointer;
  transition: all 0.3s ease;
}

.a2ui-surface-interactive:hover {
  box-shadow: var(--el-box-shadow-light);
}

.a2ui-surface-header {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background-color: var(--el-fill-color-light);
}

.a2ui-surface-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.a2ui-surface-description {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.a2ui-surface-container {
  padding: 16px;
  min-height: 100px;
}

.a2ui-surface-loading {
  padding: 20px;
}

.a2ui-surface-debug {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 16px;
}

.debug-section {
  font-size: 12px;
}

.debug-section h4 {
  margin: 8px 0 4px 0;
  font-weight: 600;
}

.debug-section code,
.debug-section pre {
  background-color: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
}
</style>
