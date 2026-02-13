/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Integration Module
 *
 * This module provides integration with Google's A2UI (Agent-to-User Interface) framework.
 * A2UI enables AI agents to generate declarative, safe, cross-platform native UI components.
 *
 * Official Documentation: https://github.com/google/A2UI
 *
 * @module a2ui
 */

// Re-export everything from the official A2UI web_core library
// Note: We're using TypeScript source directly since the pre-built dist isn't available
// In production, this would import from the compiled dist: export * from './web_core/index.js'

export type {
  // Core types
  ServerToClientMessage,
  ClientToServerMessage as A2UIClientEventMessage,
  UserAction,
  Surface,
  AnyComponentNode,

  // Component nodes
  TextNode,
  ImageNode,
  IconNode,
  VideoNode,
  AudioPlayerNode,
  RowNode,
  ColumnNode,
  ListNode,
  CardNode,
  TabsNode,
  DividerNode,
  ModalNode,
  ButtonNode,
  CheckboxNode,
  TextFieldNode,
  DateTimeInputNode,
  MultipleChoiceNode,
  SliderNode,
  CustomNode,

  // Component properties
  ResolvedText,
  ResolvedImage,
  ResolvedIcon,
  ResolvedVideo,
  ResolvedAudioPlayer,
  ResolvedRow,
  ResolvedColumn,
  ResolvedButton,
  ResolvedList,
  ResolvedCard,
  ResolvedTabs,
  ResolvedModal,
  ResolvedDivider,
  ResolvedCheckbox,
  ResolvedTextField,
  ResolvedDateTimeInput,
  ResolvedMultipleChoice,
  ResolvedSlider,

  // Data model types
  DataValue,
  DataObject,
  DataMap,
  DataArray,
  ValueMap,
  ResolvedValue,
  ResolvedMap,
  ResolvedArray,

  // Message types
  BeginRenderingMessage,
  SurfaceUpdateMessage,
  DataModelUpdate,
  DeleteSurfaceMessage,
  ComponentInstance,
  ComponentProperties,

  // Message processor interface
  MessageProcessor,
} from '../../../deps/A2UI/renderers/web_core/src/v0_8/types/types'

// Export component interfaces
export type {
  Action,
  Text,
  Image,
  Icon,
  Video,
  AudioPlayer,
  Tabs,
  Divider,
  Modal,
  Button,
  Checkbox,
  TextField,
  DateTimeInput,
  MultipleChoice,
  Slider,
  Row,
  Column,
  List,
  Card,
} from '../../../deps/A2UI/renderers/web_core/src/v0_8/types/components'

// Export primitives
export type {
  StringValue,
} from '../../../deps/A2UI/renderers/web_core/src/v0_8/types/primitives'

/**
 * Vue-specific A2UI adapter types
 */

/**
 * A2UI component type mapping for Vue/Element Plus
 */
export const A2UI_COMPONENT_TYPES = {
  // Layout components
  ROW: 'Row',
  COLUMN: 'Column',
  LIST: 'List',
  CARD: 'Card',
  TABS: 'Tabs',
  MODAL: 'Modal',

  // Display components
  TEXT: 'Text',
  IMAGE: 'Image',
  ICON: 'Icon',
  VIDEO: 'Video',
  AUDIO_PLAYER: 'AudioPlayer',
  DIVIDER: 'Divider',

  // Interactive components
  BUTTON: 'Button',
  TEXT_FIELD: 'TextField',
  CHECKBOX: 'CheckBox',
  DATE_TIME_INPUT: 'DateTimeInput',
  MULTIPLE_CHOICE: 'MultipleChoice',
  SLIDER: 'Slider',
} as const

/**
 * Vue-specific component props adapter
 * Converts A2UI props to Element Plus compatible props
 */
export interface VueA2UIAdapterProps {
  componentType: keyof typeof A2UI_COMPONENT_TYPES
  a2uiProps: Record<string, unknown>
  dataModel: Record<string, unknown>
}

/**
 * User action payload sent from frontend to backend
 */
export interface A2UIUserActionPayload {
  surfaceId: string
  componentId: string
  actionName: string
  timestamp: string
  context?: Record<string, unknown>
}

/**
 * A2UI surface metadata
 */
export interface A2UISurfaceMetadata {
  title?: string
  description?: string
  interactive?: boolean
  layout?: 'vertical' | 'horizontal' | 'grid'
}

/**
 * A2UI surface content block for chat messages
 */
export interface A2UISurfaceContentBlock {
  type: 'a2ui_surface'
  surfaceId: string
  surfaceType: 'form' | 'dashboard' | 'visualization' | 'custom'
  components: ComponentInstance[]
  dataModel: DataMap
  metadata?: A2UISurfaceMetadata
}
