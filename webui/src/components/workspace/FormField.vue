/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-form-item :label="fieldLabel" :required="isRequired">
    <!-- String type: text input or password -->
    <el-input
      v-if="fieldSchema.type === 'string' && !fieldSchema.enum"
      :type="inputType"
      :model-value="modelValue"
      :placeholder="fieldSchema.description || `请输入${fieldLabel}`"
      :show-password="inputType === 'password'"
      clearable
      @update:model-value="$emit('update:modelValue', $event)"
    />

    <!-- Enum type: select dropdown -->
    <el-select
      v-else-if="fieldSchema.enum"
      :model-value="modelValue"
      :placeholder="`请选择${fieldLabel}`"
      style="width: 100%"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option
        v-for="option in fieldSchema.enum"
        :key="option"
        :label="option"
        :value="option"
      />
    </el-select>

    <!-- Boolean type: switch -->
    <el-switch
      v-else-if="fieldSchema.type === 'boolean'"
      :model-value="modelValue"
      @update:model-value="$emit('update:modelValue', $event)"
    />

    <!-- Number/Integer type: number input -->
    <el-input-number
      v-else-if="fieldSchema.type === 'number' || fieldSchema.type === 'integer'"
      :model-value="modelValue"
      :min="fieldSchema.minimum"
      :max="fieldSchema.maximum"
      :step="fieldSchema.type === 'integer' ? 1 : 0.1"
      style="width: 100%"
      @update:model-value="$emit('update:modelValue', $event)"
    />

    <!-- Array type: tags or select with multiple -->
    <el-select
      v-else-if="fieldSchema.type === 'array' && fieldSchema.items?.enum"
      :model-value="modelValue"
      multiple
      :placeholder="`请选择${fieldLabel}`"
      style="width: 100%"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <el-option
        v-for="option in fieldSchema.items.enum"
        :key="option"
        :label="option"
        :value="option"
      />
    </el-select>

    <!-- Array type: text input for comma-separated values -->
    <el-input
      v-else-if="fieldSchema.type === 'array'"
      :model-value="arrayInputValue"
      :placeholder="`请输入${fieldLabel}，用逗号分隔`"
      @blur="handleArrayInputBlur"
      @update:model-value="arrayInputValue = $event"
    />

    <!-- Object type: JSON editor (simplified) -->
    <el-input
      v-else-if="fieldSchema.type === 'object'"
      :model-value="objectInputValue"
      type="textarea"
      :rows="4"
      :placeholder="`请输入JSON格式的${fieldLabel}`"
      @blur="handleObjectInputBlur"
      @update:model-value="objectInputValue = $event"
    />

    <!-- Fallback for unsupported types -->
    <el-input
      v-else
      :model-value="modelValue"
      :placeholder="`请输入${fieldLabel}`"
      @update:model-value="$emit('update:modelValue', $event)"
    />

    <!-- Field description -->
    <div v-if="fieldSchema.description" class="field-description">
      {{ fieldSchema.description }}
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  fieldName: string
  fieldSchema: unknown
  modelValue: unknown
}

interface Emits {
  (e: 'update:modelValue', value: unknown): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Compute field label from schema
const fieldLabel = computed(() => {
  return props.fieldSchema.title || props.fieldName
})

// Check if field is required
const isRequired = computed(() => {
  // Check if field is in required array of parent schema
  return props.fieldSchema.required || false
})

// Determine input type for string fields
const inputType = computed(() => {
  const fieldName = props.fieldName.toLowerCase()
  const description = (props.fieldSchema.description || '').toLowerCase()

  // Detect password/secret/token fields
  if (
    fieldName.includes('secret') ||
    fieldName.includes('password') ||
    fieldName.includes('token') ||
    description.includes('密码') ||
    description.includes('密钥') ||
    props.fieldSchema['x-secret']
  ) {
    return 'password'
  }

  // Detect URL fields
  if (
    fieldName.includes('url') ||
    fieldName.includes('endpoint') ||
    props.fieldSchema.format === 'uri'
  ) {
    return 'url'
  }

  // Detect email fields
  if (fieldName.includes('email') || props.fieldSchema.format === 'email') {
    return 'email'
  }

  return 'text'
})

// Handle array input (comma-separated)
const arrayInputValue = ref('')

// Watch modelValue changes to update array input
watch(() => props.modelValue, (newValue) => {
  if (Array.isArray(newValue)) {
    arrayInputValue.value = newValue.join(', ')
  }
}, { immediate: true })

const handleArrayInputBlur = () => {
  if (arrayInputValue.value.trim()) {
    const items = arrayInputValue.value
      .split(',')
      .map(s => s.trim())
      .filter(s => s.length > 0)
    emit('update:modelValue', items)
  } else {
    emit('update:modelValue', [])
  }
}

// Handle object input (JSON)
const objectInputValue = ref('')

// Watch modelValue changes to update object input
watch(() => props.modelValue, (newValue) => {
  if (typeof newValue === 'object' && newValue !== null) {
    objectInputValue.value = JSON.stringify(newValue, null, 2)
  }
}, { immediate: true })

const handleObjectInputBlur = () => {
  if (objectInputValue.value.trim()) {
    try {
      const obj = JSON.parse(objectInputValue.value)
      emit('update:modelValue', obj)
    } catch (error) {
      // Invalid JSON, ignore
      console.error('Invalid JSON:', error)
    }
  } else {
    emit('update:modelValue', {})
  }
}
</script>

<script lang="ts">
import { watch } from 'vue'

export default {
  name: 'FormField'
}
</script>

<style scoped lang="scss">
.field-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
