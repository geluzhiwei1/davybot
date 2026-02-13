/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="plugin-config-form">
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-position="top"
      v-loading="loading"
    >
      <!-- oneOf: Authentication Method Selection (Tabs) -->
      <div v-if="schema.oneOf && schema.oneOf.length > 0" class="auth-method-selector">
        <el-form-item label="认证方式">
          <el-radio-group v-model="selectedAuthMethod" @change="onAuthMethodChange">
            <el-radio-button
              v-for="(authSchema, index) in schema.oneOf"
              :key="index"
              :label="index"
            >
              {{ getAuthMethodTitle(authSchema, index) }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
      </div>

      <!-- Regular fields (no oneOf) -->
      <template v-if="!schema.oneOf || schema.oneOf.length === 0">
        <div v-for="(fieldSchema, fieldName) in schema.properties" :key="fieldName">
          <FormField
            :field-name="fieldName"
            :field-schema="fieldSchema"
            :model-value="formData[fieldName]"
            @update:model-value="formData[fieldName] = $event"
          />
        </div>
      </template>

      <!-- Fields with oneOf: Show required fields for selected option + common fields -->
      <template v-else>
        <!-- Get required fields for selected auth method -->
        <div v-for="fieldName in getRequiredFieldsForAuthMethod(selectedAuthMethod)" :key="fieldName">
          <FormField
            v-if="schema.properties[fieldName]"
            :field-name="fieldName"
            :field-schema="schema.properties[fieldName]"
            :model-value="formData[fieldName]"
            @update:model-value="formData[fieldName] = $event"
          />
        </div>

        <!-- Common fields (not in any oneOf required) -->
        <div v-for="(fieldSchema, fieldName) in getCommonFields()" :key="fieldName">
          <FormField
            :field-name="fieldName"
            :field-schema="fieldSchema"
            :model-value="formData[fieldName]"
            @update:model-value="formData[fieldName] = $event"
          />
        </div>
      </template>

      <!-- Form actions -->
      <el-form-item>
        <el-button type="primary" @click="handleSave" :loading="saving">
          保存配置
        </el-button>
        <el-button @click="handleCancel">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { pluginsApi } from '@/services/api/plugins'
import FormField from './FormField.vue'

interface Props {
  workspaceId: string
  pluginId: string
}

interface Emits {
  (e: 'saved', config: Record<string, unknown>): void
  (e: 'cancel'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const loading = ref(false)
const saving = ref(false)
const schema = ref<unknown>({})
const existingConfig = ref<Record<string, unknown>>({})
const formData = reactive<Record<string, unknown>>({})
const formRef = ref<FormInstance>()
const selectedAuthMethod = ref(0)

// Form rules for validation
const formRules = computed<FormRules>(() => {
  const rules: FormRules = {}

  const properties = schema.value.oneOf
    ? schema.value.oneOf[selectedAuthMethod.value]?.properties
    : schema.value.properties

  if (!properties) return rules

  for (const [fieldName, fieldSchema] of Object.entries(properties)) {
    if (fieldSchema.required || schema.value.required?.includes(fieldName)) {
      rules[fieldName] = [
        {
          required: true,
          message: `${fieldSchema.title || fieldName} 是必填项`,
          trigger: 'blur'
        }
      ]
    }
  }

  return rules
})

// Load configuration schema
const loadSchema = async () => {
  loading.value = true
  try {
    const response = await pluginsApi.getConfigSchema(props.workspaceId, props.pluginId)
    schema.value = response.schema
    existingConfig.value = response.existing_config || {}

    // Initialize form data with existing config or defaults
    initializeFormData()
  } catch (error: unknown) {
    ElMessage.error(`加载配置失败: ${error.message || error}`)
  } finally {
    loading.value = false
  }
}

// Initialize form data with existing config or default values
const initializeFormData = () => {
  if (!schema.value.properties) return

  // Determine which auth method to use based on existing config
  if (schema.value.oneOf && schema.value.oneOf.length > 0) {
    // Try to detect which auth method was used from existing config
    for (let i = 0; i < schema.value.oneOf.length; i++) {
      const required = schema.value.oneOf[i].required || []
      const hasRequiredFields = required.every((field: string) =>
        existingConfig.value[field] !== undefined
      )

      if (hasRequiredFields) {
        selectedAuthMethod.value = i
        break
      }
    }

    // Initialize required auth fields
    const requiredFields = getRequiredFieldsForAuthMethod(selectedAuthMethod.value)
    requiredFields.forEach(fieldName => {
      const fieldSchema = schema.value.properties[fieldName]
      if (fieldSchema) {
        if (existingConfig.value[fieldName] !== undefined) {
          formData[fieldName] = existingConfig.value[fieldName]
        } else if (fieldSchema.default !== undefined) {
          formData[fieldName] = fieldSchema.default
        } else {
          switch (fieldSchema.type) {
            case 'boolean':
              formData[fieldName] = false
              break
            case 'number':
            case 'integer':
              formData[fieldName] = fieldSchema.minimum || 0
              break
            case 'array':
              formData[fieldName] = []
              break
            case 'object':
              formData[fieldName] = {}
              break
            default:
              formData[fieldName] = ''
          }
        }
      }
    })
  }

  // Initialize common fields
  const commonFields = getCommonFields()
  for (const [fieldName, fieldSchema] of Object.entries(commonFields)) {
    if (existingConfig.value[fieldName] !== undefined) {
      formData[fieldName] = existingConfig.value[fieldName]
    } else if (fieldSchema.default !== undefined) {
      formData[fieldName] = fieldSchema.default
    } else {
      switch (fieldSchema.type) {
        case 'boolean':
          formData[fieldName] = false
          break
        case 'number':
        case 'integer':
          formData[fieldName] = fieldSchema.minimum || 0
          break
        case 'array':
          formData[fieldName] = []
          break
        case 'object':
          formData[fieldName] = {}
          break
        default:
          formData[fieldName] = ''
      }
    }
  }
}

// Get required fields for selected auth method
const getRequiredFieldsForAuthMethod = (index: number): string[] => {
  if (!schema.value.oneOf || !schema.value.oneOf[index]) {
    return []
  }
  return schema.value.oneOf[index].required || []
}

// Get common fields (not in any oneOf required)
const getCommonFields = () => {
  if (!schema.value.properties) {
    return {}
  }

  const commonFields: Record<string, unknown> = {}

  // Collect all required fields from all oneOf options
  const allRequiredFields = new Set<string>()
  if (schema.value.oneOf) {
    for (const option of schema.value.oneOf) {
      if (option.required) {
        option.required.forEach((field: string) => allRequiredFields.add(field))
      }
    }
  }

  // Filter out fields that are in any oneOf required
  for (const [fieldName, fieldSchema] of Object.entries(schema.value.properties)) {
    if (!allRequiredFields.has(fieldName)) {
      commonFields[fieldName] = fieldSchema
    }
  }

  return commonFields
}

// Get authentication method title for oneOf tabs
const getAuthMethodTitle = (authSchema: unknown, index: number) => {
  if (authSchema.title) return authSchema.title
  if (authSchema.description) return authSchema.description

  // Default titles based on common patterns
  const properties = authSchema.properties || {}
  if (properties.app_id && properties.app_secret) {
    return 'App凭证 (推荐)'
  } else if (properties.webhook_url) {
    return 'Webhook (简单模式)'
  }

  return `方式 ${index + 1}`
}

// Handle auth method change
const onAuthMethodChange = (index: number) => {
  selectedAuthMethod.value = index

  // Clear only required auth fields, keep common fields
  const requiredFields = getRequiredFieldsForAuthMethod(index)
  requiredFields.forEach(key => delete formData[key])

  // Initialize required auth fields
  requiredFields.forEach(fieldName => {
    const fieldSchema = schema.value.properties[fieldName]
    if (fieldSchema) {
      if (fieldSchema.default !== undefined) {
        formData[fieldName] = fieldSchema.default
      } else {
        switch (fieldSchema.type) {
          case 'boolean':
            formData[fieldName] = false
            break
          case 'number':
          case 'integer':
            formData[fieldName] = fieldSchema.minimum || 0
            break
          case 'array':
            formData[fieldName] = []
            break
          case 'object':
            formData[fieldName] = {}
            break
          default:
            formData[fieldName] = ''
        }
      }
    }
  })

  // Initialize common fields if not already set
  const commonFields = getCommonFields()
  for (const [fieldName, fieldSchema] of Object.entries(commonFields)) {
    if (formData[fieldName] === undefined) {
      if (fieldSchema.default !== undefined) {
        formData[fieldName] = fieldSchema.default
      } else {
        switch (fieldSchema.type) {
          case 'boolean':
            formData[fieldName] = false
            break
          case 'number':
          case 'integer':
            formData[fieldName] = fieldSchema.minimum || 0
            break
          case 'array':
            formData[fieldName] = []
            break
          case 'object':
            formData[fieldName] = {}
            break
          default:
            formData[fieldName] = ''
        }
      }
    }
  }
}

// Validate form
const validateForm = async (): Promise<boolean> => {
  if (!formRef.value) return false

  try {
    await formRef.value.validate()
    return true
  } catch {
    return false
  }
}

// Handle save
const handleSave = async () => {
  // Validate form
  const isValid = await validateForm()
  if (!isValid) {
    ElMessage.warning('请检查表单填写是否正确')
    return
  }

  saving.value = true
  try {
    // Build config to save - include only relevant fields for oneOf
    const configToSave: Record<string, unknown> = {}

    if (schema.value.oneOf && schema.value.oneOf.length > 0) {
      // Get required fields for selected auth method
      const requiredFields = getRequiredFieldsForAuthMethod(selectedAuthMethod.value)
      requiredFields.forEach(fieldName => {
        if (formData[fieldName] !== undefined && formData[fieldName] !== '') {
          configToSave[fieldName] = formData[fieldName]
        }
      })

      // Add common fields
      const commonFields = getCommonFields()
      for (const fieldName of Object.keys(commonFields)) {
        if (formData[fieldName] !== undefined) {
          configToSave[fieldName] = formData[fieldName]
        }
      }
    } else {
      // No oneOf, include all fields
      Object.assign(configToSave, formData)
    }

    // Server-side validation
    const validation = await pluginsApi.validateConfig(
      props.workspaceId,
      props.pluginId,
      configToSave
    )

    if (!validation.valid) {
      ElMessage.error(`配置验证失败: ${validation.errors.join(', ')}`)
      return
    }

    // Save configuration
    const result = await pluginsApi.saveConfig(
      props.workspaceId,
      props.pluginId,
      configToSave
    )

    if (result.success) {
      ElMessage.success('插件配置保存成功')
      emit('saved', configToSave)
    } else {
      ElMessage.error('保存配置失败')
    }
  } catch (error: unknown) {
    ElMessage.error(`保存配置失败: ${error.message || error}`)
  } finally {
    saving.value = false
  }
}

// Handle cancel
const handleCancel = () => {
  emit('cancel')
}

// Load schema on mount
onMounted(() => {
  loadSchema()
})
</script>

<style scoped lang="scss">
.plugin-config-form {
  .auth-method-selector {
    margin-bottom: 20px;
    padding: 15px;
    background-color: var(--el-fill-color-light);
    border-radius: 4px;
  }
}
</style>
