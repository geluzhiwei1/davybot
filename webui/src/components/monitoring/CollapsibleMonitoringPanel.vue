/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="collapsible-monitoring-panel" :class="{ 'is-collapsed': isCollapsed }">
    <!-- Panel Header -->
    <div class="panel-header" @click="toggleCollapse">
      <div class="header-left">
        <el-icon class="collapse-icon" :class="{ 'is-rotated': isCollapsed }">
          <ArrowRight />
        </el-icon>
        <h3 class="panel-title">Agents</h3>
        <el-tag v-if="!isCollapsed" type="info" size="small" effect="plain">
          三级监控
        </el-tag>
      </div>
      <div class="header-right">
        <el-button :icon="Close" text circle size="small" @click.stop="handleClose" />
      </div>
    </div>

    <!-- Breadcrumb Navigation -->
    <transition name="breadcrumb-slide">
      <div v-show="!isCollapsed" class="breadcrumb-bar">
        <div class="breadcrumb-content">
          <el-breadcrumb separator="→">
            <el-breadcrumb-item
              :class="{ 'is-clickable': monitoringStore.viewState.currentLevel !== 'agents_overview' }"
              @click="handleBreadcrumbClick('agents_overview')"
            >
              <el-icon><Monitor /></el-icon>
              所有 Agents
              <el-badge
                v-if="monitoringStore.agentsStatistics.total > 0"
                :value="monitoringStore.agentsStatistics.total"
                class="breadcrumb-badge"
              />
            </el-breadcrumb-item>
            <el-breadcrumb-item
              v-if="monitoringStore.viewState.selectedAgentId"
              :class="{ 'is-clickable': monitoringStore.viewState.currentLevel !== 'task_graph' }"
              @click="handleBreadcrumbClick('task_graph')"
            >
              <el-icon><Grid /></el-icon>
              {{ selectedAgentName }}
            </el-breadcrumb-item>
            <el-breadcrumb-item v-if="monitoringStore.viewState.selectedTaskNodeId">
              <el-icon><List /></el-icon>
              {{ selectedNodeName }}
            </el-breadcrumb-item>
          </el-breadcrumb>
          <el-button
            v-if="canGoBack"
            :icon="ArrowLeft"
            size="small"
            type="primary"
            @click="handleGoBack"
          >
            返回
          </el-button>
        </div>
      </div>
    </transition>

    <!-- Panel Content -->
    <transition name="panel-slide">
      <div v-show="!isCollapsed" class="panel-content">
        <ThreeLevelMonitoringPanel />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElIcon, ElTag, ElButton, ElBreadcrumb, ElBreadcrumbItem, ElBadge } from 'element-plus'
import { ArrowRight, Close, ArrowLeft, Monitor, Grid, List } from '@element-plus/icons-vue'
import ThreeLevelMonitoringPanel from './ThreeLevelMonitoringPanel.vue'
import { useMonitoringStore } from '@/stores/monitoringStore'
import { MonitoringLevel } from '@/stores/monitoringStore'

const emit = defineEmits<{
  close: []
}>()

const monitoringStore = useMonitoringStore()
const isCollapsed = ref(false) // 默认展开，显示实时TODO列表

// 是否可以返回
const canGoBack = computed(() => {
  return monitoringStore.viewState.currentLevel !== MonitoringLevel.AGENTS_OVERVIEW
})

// 选中的Agent名称
const selectedAgentName = computed(() => {
  if (!monitoringStore.selectedAgentId) return ''
  const agent = monitoringStore.selectedAgent
  return agent?.taskName || agent?.description || monitoringStore.selectedAgentId.slice(0, 8)
})

// 选中的节点名称
const selectedNodeName = computed(() => {
  if (!monitoringStore.selectedTaskNodeId) return ''
  const node = monitoringStore.selectedTaskNode
  return node?.description || monitoringStore.selectedTaskNodeId.slice(0, 8)
})

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const handleClose = () => {
  emit('close')
}

// 处理面包屑点击
const handleBreadcrumbClick = (level: string) => {
  if (level === 'agents_overview') {
    monitoringStore.setCurrentLevel(MonitoringLevel.AGENTS_OVERVIEW)
  } else if (level === 'task_graph') {
    monitoringStore.setCurrentLevel(MonitoringLevel.TASK_GRAPH)
  }
}

// 返回上一级
const handleGoBack = () => {
  monitoringStore.goBack()
}

// 监听agent启动事件，自动展开Agents
const handleAgentStart = () => {
  isCollapsed.value = false
}

onMounted(() => {
  window.addEventListener('agent-start', handleAgentStart)
})

onUnmounted(() => {
  window.removeEventListener('agent-start', handleAgentStart)
})
</script>

<style scoped>
.collapsible-monitoring-panel {
  position: fixed;
  top: 64px;
  right: 0;
  width: 600px;
  max-width: 85vw;
  max-height: calc(100vh - 64px);
  background: var(--el-bg-color-overlay);
  border-left: 1px solid var(--el-border-color-light);
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.collapsible-monitoring-panel.is-collapsed {
  width: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--el-fill-color-extra-light);
  border-bottom: 1px solid var(--el-border-color-light);
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.panel-header:hover {
  background: var(--el-fill-color-light);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.collapse-icon {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.collapse-icon.is-rotated {
  transform: rotate(0deg);
}

.collapse-icon:not(.is-rotated) {
  transform: rotate(90deg);
}

.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--el-bg-color-page);
}

/* Breadcrumb Navigation */
.breadcrumb-bar {
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  overflow-x: auto;
}

.breadcrumb-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: max-content;
}

.el-breadcrumb {
  flex: 1;
  white-space: nowrap;
}

.el-breadcrumb-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.el-breadcrumb-item.is-clickable {
  cursor: pointer;
  transition: opacity 0.2s;
}

.el-breadcrumb-item.is-clickable:hover {
  opacity: 0.7;
}

.breadcrumb-badge {
  margin-left: 4px;
}

/* Slide animation */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.panel-slide-enter-to,
.panel-slide-leave-from {
  max-height: calc(100vh - 120px);
  opacity: 1;
}

/* Breadcrumb slide animation */
.breadcrumb-slide-enter-active,
.breadcrumb-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.breadcrumb-slide-enter-from,
.breadcrumb-slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.breadcrumb-slide-enter-to,
.breadcrumb-slide-leave-from {
  max-height: 60px;
  opacity: 1;
}

/* Responsive design */
@media (max-width: 768px) {
  .collapsible-monitoring-panel {
    width: 100vw;
    max-width: 100vw;
  }

  .panel-header {
    padding: 10px 12px;
  }

  .panel-title {
    font-size: 13px;
  }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .collapsible-monitoring-panel {
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
  }
}
</style>
