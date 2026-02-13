/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Component Mapper
 *
 * Maps A2UI component types to Element Plus Vue components
 */

import type { AnyComponentNode } from '@/a2ui'

// Element Plus component imports
import {
  ElRow,
  ElCol,
  ElCard,
  ElButton,
  ElInput,
  ElCheckbox,
  ElSwitch,
  ElSlider,
  ElTabs,
  ElDialog,
  ElDivider,
  ElText,
  ElImage,
  ElIcon,
} from 'element-plus'

/**
 * A2UI component type → Element Plus component mapping
 */
export const A2UI_COMPONENT_MAP: Record<string, unknown> = {
  // Layout components
  'Row': ElRow,
  'Column': ElCol,
  'Card': ElCard,
  'List': 'div',  // Fallback to div with custom rendering
  'Tabs': ElTabs,
  'Modal': ElDialog,

  // Display components
  'Text': ElText,
  'Image': ElImage,
  'Icon': ElIcon,
  'Divider': ElDivider,

  // Interactive components
  'Button': ElButton,
  'TextField': ElInput,
  'CheckBox': ElCheckbox,
  'Switch': ElSwitch,
  'Slider': ElSlider,
  'DateTimeInput': 'el-date-picker',
  'MultipleChoice': 'el-checkbox-group',
  'AudioPlayer': 'audio',
  'Video': 'video',
}

/**
 * Props transformer: converts A2UI props to Element Plus props
 */
export function transformProps(
  componentType: string,
  a2uiProps: Record<string, unknown>
): Record<string, unknown> {
  switch (componentType) {
    case 'Button': {
      return {
        type: a2uiProps.variant || 'default',
        size: a2uiProps.size || 'default',
        disabled: a2uiProps.disabled || false,
      }
    }

    case 'TextField': {
      return {
        modelValue: a2uiProps.value,
        placeholder: a2uiProps.placeholder,
        type: a2uiProps.type === 'number' ? 'number' : 'text',
        disabled: a2uiProps.disabled || false,
      }
    }

    case 'CheckBox': {
      return {
        modelValue: a2uiProps.value,
        label: a2uiProps.label,
        disabled: a2uiProps.disabled || false,
      }
    }

    case 'Slider': {
      return {
        modelValue: a2uiProps.value,
        min: a2uiProps.min || 0,
        max: a2uiProps.max || 100,
        step: a2uiProps.step || 1,
        disabled: a2uiProps.disabled || false,
      }
    }

    case 'Tabs': {
      return {
        modelValue: a2uiProps.activeTab || 0,
        type: a2uiProps.variant || '',
      }
    }

    case 'Row': {
      return {
        justify: a2uiProps.distribution || 'start',
        align: a2uiProps.alignment || 'top',
        gutter: a2uiProps.spacing || 0,
      }
    }

    case 'Column': {
      return {
        span: a2uiProps.span || 24,
        offset: a2uiProps.offset || 0,
      }
    }

    case 'Card': {
      return {
        shadow: a2uiProps.elevation || 'always',
        bodyStyle: a2uiProps.style || {},
      }
    }

    case 'Image': {
      return {
        src: a2uiProps.url,
        fit: a2uiProps.fit || 'cover',
        style: { maxWidth: '100%' },
      }
    }

    case 'Text': {
      return {
        tag: a2uiProps.usageHint || 'p',
        style: { margin: 0 },
      }
    }

    case 'Divider': {
      return {
        direction: a2uiProps.axis || 'horizontal',
        borderStyle: a2uiProps.style || 'solid',
      }
    }

    default:
      return a2uiProps
  }
}

/**
 * Get children components from a component node
 */
export function getComponentChildren(node: AnyComponentNode): AnyComponentNode[] {
  switch (node.type) {
    case 'Row':
      return node.properties.children || []
    case 'Column':
      return node.properties.children || []
    case 'List':
      return node.properties.children || []
    case 'Card':
      // Card can have both child and children
      if (node.properties.child) {
        return [node.properties.child]
      }
      return node.properties.children || []
    case 'Tabs':
      return node.properties.tabItems?.map((tab: unknown) => tab.child) || []
    case 'Modal':
      return [
        node.properties.entryPointChild,
        node.properties.contentChild,
      ].filter(Boolean)
    case 'Button':
      return node.properties.child ? [node.properties.child] : []
    default:
      return []
  }
}

/**
 * Check if a component is a container (has children)
 */
export function isContainerComponent(node: AnyComponentNode): boolean {
  return [
    'Row',
    'Column',
    'List',
    'Card',
    'Tabs',
    'Modal',
  ].includes(node.type)
}

/**
 * Get A2UI component display name
 */
export function getComponentDisplayName(node: AnyComponentNode): string {
  return `${node.type} (${node.id})`
}
