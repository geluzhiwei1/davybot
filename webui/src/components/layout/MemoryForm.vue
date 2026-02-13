/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-form
    ref="formRef"
    :model="formData"
    :rules="formRules"
    label-width="100px"
    class="memory-form"
  >
    <el-form-item :label="t('memory.subject')" prop="subject">
      <el-input
        v-model="formData.subject"
        :placeholder="t('memory.subjectPlaceholder')"
      />
    </el-form-item>

    <el-form-item :label="t('memory.predicate')" prop="predicate">
      <el-select
        v-model="formData.predicate"
        filterable
        allow-create
        :placeholder="t('memory.predicatePlaceholder')"
      >
        <el-option
          v-for="pred in commonPredicates"
          :key="pred"
          :label="pred"
          :value="pred"
        />
      </el-select>
    </el-form-item>

    <el-form-item :label="t('memory.object')" prop="object">
      <el-input
        v-model="formData.object"
        type="textarea"
        :rows="3"
        :placeholder="t('memory.objectPlaceholder')"
      />
    </el-form-item>

    <el-form-item :label="t('memory.type')" prop="memory_type">
      <el-select v-model="formData.memory_type" :placeholder="t('memory.selectType')">
        <el-option label="Fact" value="fact" />
        <el-option label="Preference" value="preference" />
        <el-option label="Procedure" value="procedure" />
        <el-option label="Context" value="context" />
        <el-option label="Strategy" value="strategy" />
        <el-option label="Episode" value="episode" />
      </el-select>
    </el-form-item>

    <el-form-item :label="t('memory.confidence')">
      <el-slider v-model="formData.confidence" :min="0" :max="1" :step="0.1" />
      <span class="value-display">{{ (formData.confidence * 100).toFixed(0) }}%</span>
    </el-form-item>

    <el-form-item :label="t('memory.keywords')">
      <el-select
        v-model="formData.keywords"
        multiple
        filterable
        allow-create
        :placeholder="t('memory.addKeywords')"
      >
      </el-select>
    </el-form-item>

    <el-form-item>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        {{ t('common.save') }}
      </el-button>
      <el-button @click="handleCancel">
        {{ t('common.cancel') }}
      </el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance, FormRules } from 'element-plus'
import type { CreateMemoryParams } from '@/types/memory'

const emit = defineEmits<{
  submit: [params: CreateMemoryParams]
  cancel: []
}>()

const { t } = useI18n()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const formData = reactive<CreateMemoryParams>({
  subject: '',
  predicate: 'prefers',
  object: '',
  memory_type: 'fact' as unknown,
  confidence: 0.8,
  energy: 1.0,
  keywords: []
})

const commonPredicates = [
  'prefers',
  'uses',
  'requires',
  'knows',
  'wants',
  'needs',
  'has',
  'is',
  'contains',
  'created',
  'modified',
  'learned',
  'dislikes'
]

const formRules: FormRules = {
  subject: [
    { required: true, message: t('memory.subjectRequired'), trigger: 'blur' }
  ],
  predicate: [
    { required: true, message: t('memory.predicateRequired'), trigger: 'blur' }
  ],
  object: [
    { required: true, message: t('memory.objectRequired'), trigger: 'blur' }
  ],
  memory_type: [
    { required: true, message: t('memory.typeRequired'), trigger: 'change' }
  ]
}

async function handleSubmit() {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    submitting.value = true

    emit('submit', { ...formData })
  } catch (error) {
    console.error('Form validation failed:', error)
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.memory-form {
  padding: 12px 0;
}

.value-display {
  margin-left: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
</style>
