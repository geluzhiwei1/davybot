/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="html-viewer" v-if="!error">
    <!-- 打开按钮 -->
    <div class="open-button-wrapper">
      <el-button
        type="primary"
        size="small"
        @click="openInNewTab"
      >
        <el-icon><View /></el-icon>
        在新页面打开
      </el-button>
    </div>

    <!-- HTML 内容显示区域 -->
    <div class="html-content-wrapper" v-loading="loading" element-loading-text="加载中...">
      <iframe
        ref="iframeRef"
        :srcdoc="htmlContent"
        :sandbox="sandboxAttributes"
        :data-html-content="htmlContent"
        class="html-iframe"
        @load="onFrameLoad"
      ></iframe>
    </div>

    <!-- 错误提示 -->
    <el-empty
      v-if="error"
      description="HTML 加载失败"
      :image-size="100"
    >
      <el-button type="primary" @click="reloadHTML">重新加载</el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElEmpty, ElButton, ElMessage, ElIcon } from 'element-plus'
import { View } from '@element-plus/icons-vue'

interface Props {
  modelValue: string // HTML 内容
  filename?: string // 文件名（可选）
}

const props = defineProps<Props>()

// Refs
const iframeRef = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const error = ref(false)

// 计算属性
const htmlContent = computed(() => {
  if (!props.modelValue) return ''

  let html = props.modelValue

  // 添加 base 标签以确保相对路径正确解析
  if (!html.includes('<base')) {
    const baseTag = '<base href="." target="_blank">'
    html = html.replace(/<head>/i, `<head>${baseTag}`)
  }

  return html
})

// sandbox 属性（安全沙盒配置）
const sandboxAttributes = computed(() => {
  // allow-scripts: 允许执行JavaScript
  // allow-forms: 允许提交表单
  // allow-modals: 允许模态框
  // allow-popups-to-escape-sandbox: 允许打开新窗口并跳出沙盒
  return 'allow-scripts allow-forms allow-modals allow-popups-to-escape-sandbox'
})

// 方法
const reloadHTML = () => {
  loading.value = true
  error.value = false

  if (iframeRef.value) {
    iframeRef.value.src = ''
    iframeRef.value.srcdoc = htmlContent.value
    console.log('[HTMLViewer] iframe reloaded with srcdoc, length:', htmlContent.value.length)
  }
}

const onFrameLoad = () => {
  loading.value = false
  console.log('[HTMLViewer] HTML loaded successfully')
}

const openInNewTab = () => {
  const newWindow = window.open('', '_blank')
  if (newWindow) {
    newWindow.document.write(htmlContent.value)
    newWindow.document.close()
    console.log('[HTMLViewer] Opened in new tab')
  } else {
    ElMessage.warning('无法打开新标签页')
  }
}

// 生命周期
onMounted(() => {
  console.log('[HTMLViewer] Component mounted')
  loading.value = true
  nextTick(() => {
    reloadHTML()
  })
})

// 监听内容变化
watch(() => props.modelValue, (newVal, oldVal) => {
  console.log('[HTMLViewer] props.modelValue changed:', {
    oldLength: oldVal?.length,
    newLength: newVal?.length,
    isDifferent: oldVal !== newVal
  })
  if (oldVal !== newVal) {
    reloadHTML()
  }
})

watch(htmlContent, (newVal) => {
  console.log('[HTMLViewer] htmlContent changed, length:', newVal?.length)
  if (iframeRef.value) {
    iframeRef.value.src = ''
    iframeRef.value.srcdoc = newVal
  }
})
</script>

<style scoped>
.html-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
  overflow: hidden;
  position: relative;
}

.open-button-wrapper {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 100;
}

.html-content-wrapper {
  flex: 1;
  overflow: auto;
  position: relative;
  background: white;
  min-height: 0;
}

.html-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}

/* 暗色主题适配 */
.dark .html-content-wrapper {
  background: #1d1e1f;
}
</style>
