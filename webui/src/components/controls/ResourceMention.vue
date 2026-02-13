/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <!-- 遮罩层 -->
    <div v-if="visible" class="resource-mention-backdrop" @click="close"></div>

    <!-- 弹出框 -->
    <div v-if="visible" class="resource-mention-popup" :style="popupStyle">
      <!-- Tab切换 -->
      <div class="mention-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-button', { active: activeTab === tab.key }]"
          @click="switchTab(tab.key)"
          type="button"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
          <span v-if="tab.count !== undefined" class="tab-count">{{ tab.count || 0 }}</span>
        </button>
      </div>

      <!-- 搜索框 -->
      <div class="mention-search">
        <input
          ref="searchInput"
          v-model="searchQuery"
          type="text"
          :placeholder="searchPlaceholder"
          class="mention-input"
          @keydown.down.prevent="selectNext"
          @keydown.up.prevent="selectPrevious"
          @keydown.enter.prevent="selectCurrent"
          @keydown.esc.prevent="close"
        />
      </div>

      <!-- 内容区域 -->
      <div class="mention-content">
        <!-- 文件列表 -->
        <div v-if="activeTab === 'files'" class="resource-list" ref="resourceList">
          <div
            v-for="(file, index) in filteredFiles"
            :key="file.path"
            :class="[
              'resource-item',
              'file-item',
              { 'resource-item--selected': index === selectedIndex }
            ]"
            @click="selectFile(file)"
            @mouseenter="selectedIndex = index"
          >
            <span class="item-icon">{{ getFileIcon(file) }}</span>
            <div class="item-info">
              <div class="item-name">{{ file.name }}</div>
              <div class="item-path">{{ file.path }}</div>
            </div>
            <div v-if="file.size" class="item-meta">
              <span class="item-size">{{ formatFileSize(file.size) }}</span>
            </div>
          </div>
          <div v-if="filteredFiles.length === 0" class="resource-empty">
            <span class="empty-icon">📭</span>
            <span class="empty-text">没有找到匹配的文件</span>
          </div>
        </div>

        <!-- 技能列表 -->
        <div v-else-if="activeTab === 'skills'" class="resource-list" ref="resourceList">
          <div
            v-for="(skill, index) in filteredSkills"
            :key="skill.name"
            :class="[
              'resource-item',
              'skill-item',
              { 'resource-item--selected': index === selectedIndex }
            ]"
            @click="selectSkill(skill)"
            @mouseenter="selectedIndex = index"
          >
            <span class="item-icon">{{ skill.icon }}</span>
            <div class="item-info">
              <div class="item-name">{{ skill.name }}</div>
              <div class="item-description">{{ skill.description }}</div>
            </div>
            <div class="item-meta">
              <span v-if="skill.category" class="item-badge">{{ skill.category }}</span>
              <span v-if="skill.mode" class="item-badge mode-badge">{{ skill.mode }}</span>
            </div>
          </div>
          <div v-if="filteredSkills.length === 0" class="resource-empty">
            <span class="empty-icon">⚡</span>
            <span class="empty-text">没有找到匹配的技能</span>
          </div>
        </div>

        <!-- 最近使用 -->
        <div v-else-if="activeTab === 'recent'" class="resource-list" ref="resourceList">
          <div
            v-for="(item, index) in filteredRecent"
            :key="item.id"
            :class="[
              'resource-item',
              `item-${item.type}`,
              { 'resource-item--selected': index === selectedIndex }
            ]"
            @click="selectRecent(item)"
            @mouseenter="selectedIndex = index"
          >
            <span class="item-icon">{{ item.icon }}</span>
            <div class="item-info">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-type">{{ item.type === 'skill' ? '技能' : '文件' }}</div>
            </div>
            <div class="item-meta">
              <span class="item-time">{{ formatTime(item.timestamp) }}</span>
            </div>
          </div>
          <div v-if="filteredRecent.length === 0" class="resource-empty">
            <span class="empty-icon">🕐</span>
            <span class="empty-text">暂无最近使用</span>
          </div>
        </div>
      </div>

      <!-- 底部提示 -->
      <div class="mention-footer">
        <span class="footer-hint">↑↓ 选择 | Enter 确认 | Tab 切换 | Esc 取消</span>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { apiManager } from '@/services/api'

interface FileItem {
  path: string
  name: string
  type: 'file' | 'directory'
  size?: number
  language?: string
}

interface Skill {
  name: string
  description: string
  mode?: string
  scope?: string
  icon: string
  category?: string
}

interface RecentItem {
  id: string
  type: 'file' | 'skill'
  name: string
  path?: string
  icon: string
  timestamp: number
}

interface Props {
  visible: boolean
  position: { x: number; y: number }
  workspaceId?: string
  fileTree?: unknown[]
  onSelect: (item: FileItem | Skill, type: string) => void
  onClose: () => void
}

const props = withDefaults(defineProps<Props>(), {
  workspaceId: 'default'
})


// 响应式数据
const activeTab = ref('files')
const searchQuery = ref('')
const selectedIndex = ref(0)
const searchInput = ref<HTMLInputElement>()
const resourceList = ref<HTMLElement>()

const files = ref<FileItem[]>([])
const skills = ref<Skill[]>([])
const recentItems = ref<RecentItem[]>([])

// Tab配置
const tabs = computed(() => {
  const tabsList = [
    { key: 'files', label: '文件', icon: '📁', count: files.value.length },
    { key: 'skills', label: '技能', icon: '⚡', count: skills.value.length },
    { key: 'recent', label: '最近', icon: '🕐', count: recentItems.value.length }
  ]
  console.log('[ResourceMention] Tabs computed:', tabsList)
  return tabsList
})

// 计算属性
const searchPlaceholder = computed(() => {
  switch (activeTab.value) {
    case 'files': return '搜索文件...'
    case 'skills': return '搜索技能...'
    case 'recent': return '搜索最近使用...'
    default: return '搜索...'
  }
})

const filteredFiles = computed(() => {
  if (!searchQuery.value.trim()) {
    return files.value.slice(0, 20)
  }

  const query = searchQuery.value.toLowerCase()
  return files.value
    .filter(file =>
      file.name.toLowerCase().includes(query) ||
      file.path.toLowerCase().includes(query)
    )
    .slice(0, 20)
})

const filteredSkills = computed(() => {
  if (!searchQuery.value.trim()) {
    return skills.value.slice(0, 20)
  }

  const query = searchQuery.value.toLowerCase()
  return skills.value
    .filter(skill =>
      skill.name.toLowerCase().includes(query) ||
      skill.description.toLowerCase().includes(query) ||
      (skill.category && skill.category.toLowerCase().includes(query))
    )
    .slice(0, 20)
})

const filteredRecent = computed(() => {
  if (!searchQuery.value.trim()) {
    return recentItems.value.slice(0, 20)
  }

  const query = searchQuery.value.toLowerCase()
  return recentItems.value
    .filter(item =>
      item.name.toLowerCase().includes(query)
    )
    .slice(0, 20)
})

const popupStyle = computed(() => {
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const popupWidth = 560
  const popupHeight = 480

  // 计算最佳位置
  let left = props.position.x
  let top = props.position.y

  // 确保不超出右边界
  if (left + popupWidth > viewportWidth) {
    left = viewportWidth - popupWidth - 20
  }

  // 确保不超出下边界
  if (top + popupHeight > viewportHeight) {
    top = viewportHeight - popupHeight - 20
  }

  // 确保不超出左边界和上边界
  left = Math.max(20, left)
  top = Math.max(20, top)

  return {
    left: `${left}px`,
    top: `${top}px`,
    position: 'fixed' as const,
    width: `${popupWidth}px`,
    maxHeight: `${popupHeight}px`,
    zIndex: 10000
  }
})

// 方法
const loadFiles = async () => {
  try {
    let fileTreeData = props.fileTree || []

    if (fileTreeData.length === 0) {
      const response = await apiManager.getWorkspacesApi().getFileTree(props.workspaceId)
      fileTreeData = response || []
    }

    const flattenFiles = (items: unknown[], parentPath = ''): FileItem[] => {
      const result: FileItem[] = []

      for (const item of items) {
        const fullPath = parentPath ? `${parentPath}/${item.name}` : item.name

        if (item.type === 'directory' || item.type === 'folder') {
          result.push({
            path: fullPath,
            name: item.name,
            type: 'directory'
          })

          if (item.children && item.children.length > 0) {
            result.push(...flattenFiles(item.children, fullPath))
          }
        } else {
          result.push({
            path: fullPath,
            name: item.name,
            type: 'file',
            size: item.size,
            language: item.language
          })
        }
      }

      return result
    }

    files.value = flattenFiles(fileTreeData)
  } catch (error) {
    console.error('Failed to load workspace files:', error)
    files.value = []
  }
}

const loadSkills = async () => {
  try {
    console.log('[ResourceMention] ===== Loading skills =====')
    console.log('[ResourceMention] Workspace ID:', props.workspaceId)

    // 使用 apiManager 调用正确的 API
    const response = await apiManager.getSkillsApi().listSkills({
      workspace_id: props.workspaceId
    })

    console.log('[ResourceMention] API Response:', response)
    skills.value = response.skills || []
    console.log('[ResourceMention] Skills loaded successfully:', skills.value.length, 'skills')
    console.log('[ResourceMention] Skills:', skills.value)
    console.log('[ResourceMention] ===== Skills loading complete =====')
  } catch (error: unknown) {
    console.error('[ResourceMention] ===== Failed to load skills =====')
    console.error('[ResourceMention] Error:', error)
    console.error('[ResourceMention] Error message:', error?.message)
    console.error('[ResourceMention] Error response:', error?.response)
    skills.value = []
  }
}

const loadRecentItems = () => {
  try {
    const stored = localStorage.getItem('resource-mention-recent')
    if (stored) {
      const items = JSON.parse(stored)
      // 只保留最近7天的记录
      const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
      recentItems.value = items.filter((item: RecentItem) => item.timestamp > weekAgo)
    }
  } catch (error) {
    console.error('Failed to load recent items:', error)
    recentItems.value = []
  }
}

const saveRecentItem = (item: RecentItem) => {
  try {
    // 移除重复项
    recentItems.value = recentItems.value.filter(i => i.id !== item.id)

    // 添加到开头
    recentItems.value.unshift(item)

    // 只保留最近50条
    recentItems.value = recentItems.value.slice(0, 50)

    // 保存到localStorage
    localStorage.setItem('resource-mention-recent', JSON.stringify(recentItems.value))
  } catch (error) {
    console.error('Failed to save recent item:', error)
  }
}

const switchTab = (tabKey: string) => {
  console.log('[ResourceMention] Switching to tab:', tabKey)
  activeTab.value = tabKey
  selectedIndex.value = 0
  searchQuery.value = ''
  nextTick(() => {
    searchInput.value?.focus()
    console.log('[ResourceMention] Tab switched to:', tabKey)
  })
}

const selectNext = () => {
  const items = getCurrentItems()
  if (selectedIndex.value < items.length - 1) {
    selectedIndex.value++
    scrollToSelected()
  }
}

const selectPrevious = () => {
  if (selectedIndex.value > 0) {
    selectedIndex.value--
    scrollToSelected()
  }
}

const selectCurrent = () => {
  const items = getCurrentItems()
  const selected = items[selectedIndex.value]

  if (activeTab.value === 'files') {
    selectFile(selected as FileItem)
  } else if (activeTab.value === 'skills') {
    selectSkill(selected as Skill)
  } else if (activeTab.value === 'recent') {
    selectRecent(selected as RecentItem)
  }
}

const selectFile = (file: FileItem) => {
  props.onSelect(file, 'file')

  // 保存到最近使用
  saveRecentItem({
    id: `file-${file.path}`,
    type: 'file',
    name: file.name,
    path: file.path,
    icon: getFileIcon(file),
    timestamp: Date.now()
  })

  close()
}

const selectSkill = (skill: Skill) => {
  props.onSelect(skill, 'skill')

  // 保存到最近使用
  saveRecentItem({
    id: `skill-${skill.name}`,
    type: 'skill',
    name: skill.name,
    icon: skill.icon,
    timestamp: Date.now()
  })

  close()
}

const selectRecent = (item: RecentItem) => {
  if (item.type === 'file') {
    const file = files.value.find(f => f.path === item.path)
    if (file) {
      selectFile(file)
    }
  } else if (item.type === 'skill') {
    const skill = skills.value.find(s => s.name === item.name)
    if (skill) {
      selectSkill(skill)
    }
  }
}

const close = () => {
  props.onClose()
}

const scrollToSelected = () => {
  nextTick(() => {
    if (resourceList.value) {
      const selectedItem = resourceList.value.children[selectedIndex.value] as HTMLElement
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest' })
      }
    }
  })
}

const getCurrentItems = () => {
  switch (activeTab.value) {
    case 'files': return filteredFiles.value
    case 'skills': return filteredSkills.value
    case 'recent': return filteredRecent.value
    default: return []
  }
}

const getFileIcon = (file: FileItem): string => {
  if (file.type === 'directory') return '📁'

  const ext = file.name.split('.').pop()?.toLowerCase()
  const icons: Record<string, string> = {
    'py': '🐍',
    'vue': '💚',
    'ts': '📘',
    'js': '📜',
    'jsx': '⚛️',
    'tsx': '⚛️',
    'md': '📝',
    'json': '📋',
    'yaml': '📋',
    'yml': '📋',
    'html': '🌐',
    'css': '🎨',
    'scss': '🎨',
    'png': '🖼️',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'gif': '🖼️',
    'svg': '🎨',
    'pdf': '📄',
    'txt': '📄'
  }

  return icons[ext || ''] || '📄'
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const formatTime = (timestamp: number): string => {
  const now = Date.now()
  const diff = now - timestamp

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

// 智能Tab切换
const switchTabBasedOnQuery = (query: string) => {
  // 如果查询看起来像文件路径
  if (query.includes('/') || query.includes('.') || query.includes('*')) {
    activeTab.value = 'files'
  }
  // 如果查询匹配技能名称
  else if (skills.value.some(s => s.name.toLowerCase().startsWith(query.toLowerCase()))) {
    activeTab.value = 'skills'
  }
  // 如果为空，显示最近使用
  else if (!query) {
    if (recentItems.value.length > 0) {
      activeTab.value = 'recent'
    }
  }
}

// 监听器
watch(() => props.visible, (visible) => {
  console.log('[ResourceMention] Visible changed:', visible)
  console.log('[ResourceMention] Workspace ID:', props.workspaceId)
  if (visible) {
    console.log('[ResourceMention] Loading data...')
    loadFiles()
    loadSkills()
    loadRecentItems()
    searchQuery.value = ''
    selectedIndex.value = 0
    nextTick(() => {
      searchInput.value?.focus()
      console.log('[ResourceMention] Data loaded:', {
        files: files.value.length,
        skills: skills.value.length,
        recent: recentItems.value.length
      })
    })
  }
})

watch(searchQuery, (newQuery) => {
  selectedIndex.value = 0
  switchTabBasedOnQuery(newQuery)
})

watch(activeTab, () => {
  selectedIndex.value = 0
})

// 键盘事件处理
const handleKeydown = (event: KeyboardEvent) => {
  if (!props.visible) return

  if (event.key === 'Tab') {
    event.preventDefault()
    const tabKeys = ['files', 'skills', 'recent']
    const currentIndex = tabKeys.indexOf(activeTab.value)
    const nextIndex = (currentIndex + 1) % tabKeys.length
    switchTab(tabKeys[nextIndex])
  }
}

// 生命周期 - 添加全局键盘监听器
onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.resource-mention-popup {
  position: fixed;
  z-index: 10000;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.resource-mention-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 9999;
  animation: fadeInBackdrop 0.2s ease-out;
}

@keyframes fadeInBackdrop {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.mention-tabs {
  display: flex !important;
  flex-direction: row !important;
  gap: 4px !important;
  padding: 8px 12px 0 !important;
  border-bottom: 2px solid #e4e7ed !important;
  background: #fafafa !important;
  position: relative !important;
  z-index: 10 !important;
  min-height: 40px !important;
}

.tab-button {
  display: flex !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 10px 16px !important;
  border: 2px solid #dcdfe6 !important;
  background: white !important;
  border-radius: 8px 8px 0 0 !important;
  cursor: pointer !important;
  transition: all 0.2s !important;
  color: #606266 !important;
  font-size: 14px !important;
  font-weight: 600 !important;
  min-width: 80px !important;
  justify-content: center !important;
  position: relative !important;
  opacity: 1 !important;
  visibility: visible !important;
}

.tab-button:hover {
  background: #f5f7fa;
  color: #409eff;
}

.tab-button.active {
  background: white;
  color: #409eff;
  border-bottom: 3px solid #409eff;
  border-color: #409eff;
  font-weight: 700;
}

.tab-icon {
  font-size: 16px;
}

.tab-label {
  font-size: 13px;
}

.tab-count {
  font-size: 11px;
  background: #e4e7ed;
  color: #909399;
  padding: 2px 6px;
  border-radius: 10px;
  font-weight: 600;
}

.tab-button.active .tab-count {
  background: #409eff;
  color: white;
}

.mention-search {
  padding: 8px 12px;
  border-bottom: 1px solid #e4e7ed;
}

.mention-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.mention-input:focus {
  border-color: #409eff;
}

.mention-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.resource-list {
  flex: 1;
  overflow-y: auto;
  max-height: 320px;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f5f5f5;
}

.resource-item:hover,
.resource-item--selected {
  background-color: #f5f7fa;
}

.resource-item--selected {
  background-color: #ecf5ff;
}

.item-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-weight: 500;
  color: #303133;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-description {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.item-path {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.item-type {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.item-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.item-size,
.item-time {
  font-size: 11px;
  color: #c0c4cc;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}

.item-badge {
  font-size: 10px;
  color: #67c23a;
  background: #e1f3d8;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.mode-badge {
  color: #409eff;
  background: #d9ecff;
}

.resource-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  color: #909399;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
}

.mention-footer {
  padding: 8px 12px;
  border-top: 1px solid #e4e7ed;
  background: #fafafa;
}

.footer-hint {
  font-size: 11px;
  color: #909399;
  text-align: center;
}

/* 滚动条样式 */
.resource-list::-webkit-scrollbar {
  width: 6px;
}

.resource-list::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.resource-list::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.resource-list::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .resource-mention-popup {
    background: #2c2c2c;
    border-color: #3a3a3a;
  }

  .mention-tabs {
    background: #1a1a1a;
    border-bottom-color: #3a3a3a;
  }

  .tab-button {
    color: #a0a0a0;
  }

  .tab-button:hover {
    background: #2a2a2a;
    color: #64b4ff;
  }

  .tab-button.active {
    background: #2c2c2c;
    color: #64b4ff;
    border-bottom-color: #64b4ff;
  }

  .mention-input {
    background: #1a1a1a;
    border-color: #3a3a3a;
    color: #e0e0e0;
  }

  .mention-input:focus {
    border-color: #64b4ff;
  }

  .resource-item:hover,
  .resource-item--selected {
    background-color: #3a3a3a;
  }

  .resource-item--selected {
    background-color: #1e3a5f;
  }

  .item-name {
    color: #e0e0e0;
  }

  .mention-footer {
    background: #1a1a1a;
    border-top-color: #3a3a3a;
  }
}
</style>
