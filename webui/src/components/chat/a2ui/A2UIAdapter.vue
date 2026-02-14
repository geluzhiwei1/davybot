/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <component
    :is="mappedComponent"
    v-if="shouldRender"
    v-bind="componentProps"
    :class="componentClasses"
    :style="componentStyles"
    @click="handleClick"
    @change="handleChange"
    @input="handleInput"
  >
    <!-- Recursively render children -->
    <template v-if="hasChildren">
      <A2UIAdapter
        v-for="child in children"
        :key="child.id"
        :node="child"
        :data-model="dataModel"
        :surface-id="surfaceId"
        @action="emitAction"
      />
    </template>

    <!-- Text content for Text component -->
    <template v-else-if="node.type === 'Text'">
      {{ textContent }}
    </template>

    <!-- Child component for Button -->
    <template v-else-if="node.type === 'Button' && buttonChild">
      <A2UIAdapter
        :node="buttonChild"
        :data-model="dataModel"
        :surface-id="surfaceId"
        @action="emitAction"
      />
    </template>

    <!-- Tab panes for Tabs -->
    <template v-else-if="node.type === 'Tabs'">
      <el-tab-pane
        v-for="(tab, index) in tabItems"
        :key="index"
        :label="tab.title"
        :name="String(index)"
      >
        <A2UIAdapter
          v-if="tab.child"
          :node="tab.child"
          :data-model="dataModel"
          :surface-id="surfaceId"
          @action="emitAction"
        />
      </el-tab-pane>
    </template>

    <!-- Default slot fallback -->
    <template v-else>
      <slot />
    </template>
  </component>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import type { AnyComponentNode } from '@/a2ui'
import {
  A2UI_COMPONENT_MAP,
  transformProps,
  getComponentChildren,
} from './utils/componentMapper'
import { parseStringValue } from './composables/useA2UIDataBinding'

const props = defineProps<{
  node: AnyComponentNode
  dataModel: Record<string, unknown>
  surfaceId: string
}>()

const emit = defineEmits<{
  action: [payload: {
    surfaceId: string
    componentId: string
    actionName: string
    timestamp: string
    context?: Record<string, unknown>
  }]
}>()

// Map to Element Plus component
const mappedComponent = computed(() => {
  const component = A2UI_COMPONENT_MAP[props.node.type]

  // Handle string component names (async components)
  if (typeof component === 'string') {
    if (component === 'div') return 'div'
    if (component === 'audio') return 'audio'
    if (component === 'video') return 'video'

    // Element Plus components
    return defineAsyncComponent(() =>
      import('element-plus')
        .then(module => {
          const componentName = component.replace('el-', '').split('-').map((part, i) =>
            i === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1)
          ).join('')
          return (module as unknown)[componentName] || component
        })
    )
  }

  return component
})

// Transform props
const componentProps = computed(() => {
  return transformProps(props.node.type, (props.node.properties as unknown) || {})
})

// Component classes
const componentClasses = computed(() => {
  const classes: string[] = [`a2ui-${props.node.type.toLowerCase()}`]

  // Add weight-based class if present
  if (props.node.weight !== undefined) {
    classes.push(`a2ui-weight-${props.node.weight}`)
  }

  return classes
})

// Component styles
const componentStyles = computed(() => {
  const styles: Record<string, string> = {}

  // Add any inline styles from properties
  if ((props.node.properties as unknown)?.style) {
    Object.assign(styles, (props.node.properties as unknown).style)
  }

  return styles
})

// Should render?
const shouldRender = computed(() => {
  // Components can be hidden via data binding
  return true // TODO: implement visibility logic
})

// Children
const children = computed(() => {
  return getComponentChildren(props.node)
})

const hasChildren = computed(() => {
  return children.value.length > 0
})

// Text content
const textContent = computed(() => {
  if (props.node.type === 'Text') {
    const textProp = (props.node.properties as unknown)?.text
    return parseStringValue(textProp, props.dataModel)
  }
  return ''
})

// Button child
const buttonChild = computed(() => {
  if (props.node.type === 'Button') {
    return (props.node.properties as unknown)?.child
  }
  return null
})

// Tab items
const tabItems = computed(() => {
  if (props.node.type === 'Tabs') {
    const items = (props.node.properties as unknown)?.tabItems || []
    return items.map((item: unknown) => ({
      title: parseStringValue(item.title, props.dataModel),
      child: item.child,
    }))
  }
  return []
})

// Event handlers
const handleClick = (event: Event) => {
  if (props.node.type === 'Button') {
    const action = (props.node.properties as unknown)?.action
    if (action) {
      emitAction(action.name, action.context, event)
    }
  }
}

const handleChange = (_value: unknown) => {
  // Handle input changes

  // Update data model if component has data binding
  if (props.node.dataContextPath) {
    // TODO: Update data model at path
  }
}

const handleInput = (_value: unknown) => {
  // Handle input events
}

const emitAction = (
  actionName: string,
  actionContext: unknown[] | undefined
) => {
  const context: Record<string, unknown> = {}

  // Resolve action context
  if (actionContext) {
    for (const ctx of actionContext) {
      const value = parseStringValue(ctx.value, props.dataModel)
      context[ctx.key] = value
    }
  }

  emit('action', {
    surfaceId: props.surfaceId,
    componentId: props.node.id,
    actionName,
    timestamp: new Date().toISOString(),
    context: Object.keys(context).length > 0 ? context : undefined,
  })
}
</script>

<style scoped>
.a2ui-row {
  display: flex;
}

.a2ui-column {
  flex: 1;
}

.a2ui-card {
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  padding: var(--el-card-padding);
}

.a2ui-button {
  margin: 4px;
}

.a2ui-text-field {
  margin: 8px 0;
}

.a2ui-checkbox {
  margin: 4px 0;
}

.a2ui-divider {
  margin: 16px 0;
}
</style>
