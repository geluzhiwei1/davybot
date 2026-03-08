/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * A2UI Component Mapper Unit Tests
 */

import { describe, it, expect } from 'vitest'
import {
  A2UI_COMPONENT_MAP,
  transformProps,
  getComponentChildren,
  isContainerComponent,
  getComponentDisplayName
} from '@/components/chat/a2ui/utils/componentMapper'

describe('Component Mapper', () => {
  describe('A2UI_COMPONENT_MAP', () => {
    it('should have mapping for all A2UI component types', () => {
      const requiredTypes = [
        'Row', 'Column', 'Card', 'List', 'Tabs', 'Modal',
        'Text', 'Image', 'Icon', 'Divider',
        'Button', 'TextField', 'CheckBox', 'Switch', 'Slider',
        'DateTimeInput', 'MultipleChoice', 'AudioPlayer', 'Video'
      ]

      requiredTypes.forEach(type => {
        expect(A2UI_COMPONENT_MAP[type]).toBeDefined()
      })
    })

    it('should map Button to Element Plus component', () => {
      expect(A2UI_COMPONENT_MAP['Button']).toBeDefined()
    })

    it('should map TextField to Element Plus input', () => {
      expect(A2UI_COMPONENT_MAP['TextField']).toBeDefined()
    })
  })

  describe('transformProps', () => {
    it('should transform Button props', () => {
      const a2uiProps = {
        variant: 'primary',
        size: 'large',
        disabled: false
      }

      const result = transformProps('Button', a2uiProps)

      expect(result).toEqual({
        type: 'primary',
        size: 'large',
        disabled: false
      })
    })

    it('should transform TextField props', () => {
      const a2uiProps = {
        value: 'john_doe',
        placeholder: 'Enter username',
        type: 'shortText'
      }

      const result = transformProps('TextField', a2uiProps)

      expect(result).toEqual({
        modelValue: 'john_doe',
        placeholder: 'Enter username',
        type: 'text',
        disabled: false
      })
    })

    it('should transform CheckBox props', () => {
      const a2uiProps = {
        value: true,
        label: 'Remember me'
      }

      const result = transformProps('CheckBox', a2uiProps)

      expect(result).toEqual({
        modelValue: true,
        label: 'Remember me',
        disabled: false
      })
    })

    it('should transform Slider props', () => {
      const a2uiProps = {
        value: 50,
        min: 0,
        max: 100,
        step: 5
      }

      const result = transformProps('Slider', a2uiProps)

      expect(result).toEqual({
        modelValue: 50,
        min: 0,
        max: 100,
        step: 5,
        disabled: false
      })
    })

    it('should transform Row props', () => {
      const a2uiProps = {
        distribution: 'spaceBetween',
        alignment: 'center',
        spacing: 16
      }

      const result = transformProps('Row', a2uiProps)

      expect(result).toEqual({
        justify: 'spaceBetween',
        align: 'center',
        gutter: 16
      })
    })

    it('should transform Column props', () => {
      const a2uiProps = {
        span: 12,
        offset: 6
      }

      const result = transformProps('Column', a2uiProps)

      expect(result).toEqual({
        span: 12,
        offset: 6
      })
    })

    it('should pass through unknown props', () => {
      const a2uiProps = {
        customProp: 'value',
        anotherProp: 123
      }

      const result = transformProps('Unknown', a2uiProps)

      expect(result).toEqual(a2uiProps)
    })
  })

  describe('getComponentChildren', () => {
    it('should return empty array for leaf components', () => {
      const textField = {
        id: 'field1',
        type: 'TextField',
        properties: {}
      }

      const children = getComponentChildren(textField as unknown)

      expect(children).toEqual([])
    })

    it('should return children for Row component', () => {
      const child1 = { id: 'child1', type: 'Text', properties: {} }
      const child2 = { id: 'child2', type: 'Text', properties: {} }

      const row = {
        id: 'row1',
        type: 'Row',
        properties: {
          children: [child1, child2]
        }
      }

      const children = getComponentChildren(row as unknown)

      expect(children).toHaveLength(2)
      expect(children[0]).toEqual(child1)
      expect(children[1]).toEqual(child2)
    })

    it('should return child for Button component', () => {
      const child = { id: 'label', type: 'Text', properties: {} }

      const button = {
        id: 'btn1',
        type: 'Button',
        properties: {
          action: { name: 'click' },
          child: child
        }
      }

      const children = getComponentChildren(button as unknown)

      expect(children).toHaveLength(1)
      expect(children[0]).toEqual(child)
    })

    it('should return tab items for Tabs component', () => {
      const tabItems = [
        {
          title: { literalString: 'Tab 1' },
          child: { id: 'tab1', type: 'Text', properties: {} }
        },
        {
          title: { literalString: 'Tab 2' },
          child: { id: 'tab2', type: 'Text', properties: {} }
        }
      ]

      const tabs = {
        id: 'tabs1',
        type: 'Tabs',
        properties: { tabItems }
      }

      const children = getComponentChildren(tabs as unknown)

      expect(children).toHaveLength(2)
    })
  })

  describe('isContainerComponent', () => {
    it('should return true for Row', () => {
      const component = { id: 'row1', type: 'Row', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return true for Column', () => {
      const component = { id: 'col1', type: 'Column', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return true for Card', () => {
      const component = { id: 'card1', type: 'Card', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return true for List', () => {
      const component = { id: 'list1', type: 'List', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return true for Tabs', () => {
      const component = { id: 'tabs1', type: 'Tabs', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return true for Modal', () => {
      const component = { id: 'modal1', type: 'Modal', properties: {} }
      expect(isContainerComponent(component as unknown)).toBe(true)
    })

    it('should return false for non-container components', () => {
      const textComponent = { id: 'text1', type: 'Text', properties: {} }
      expect(isContainerComponent(textComponent as unknown)).toBe(false)

      const buttonComponent = { id: 'btn1', type: 'Button', properties: {} }
      expect(isContainerComponent(buttonComponent as unknown)).toBe(false)
    })
  })

  describe('getComponentDisplayName', () => {
    it('should return display name with type and id', () => {
      const component = { id: 'btn1', type: 'Button', properties: {} }

      const name = getComponentDisplayName(component as unknown)

      expect(name).toBe('Button (btn1)')
    })
  })
})
