/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="path-autocomplete" ref="containerRef">
    <!-- 补全菜单 -->
    <Transition name="fade">
      <div
        v-if="showMenu && filteredItems.length > 0"
        class="autocomplete-menu"
        :style="menuStyle"
      >
        <div class="menu-header">
          <span class="menu-title">{{ menuTitle }}</span>
          <span class="menu-hint">↑↓ 选择 | Enter 确认 | Esc 取消</span>
        </div>

        <div class="menu-list">
          <div
            v-for="(item, index) in filteredItems"
            :key="item.path"
            :class="[
              'menu-item',
              {
                active: index === selectedIndex,
                folder: item.type === 'folder',
                file: item.type === 'file'
              }
            ]"
            @click="selectItem(index)"
            @mouseenter="selectedIndex = index"
          >
            <span class="item-icon">{{ getItemIcon(item) }}</span>
            <span class="item-name">{{ item.name }}</span>
            <span v-if="item.type === 'folder'" class="item-suffix">/</span>
            <span class="item-path">{{ item.displayPath }}</span>
          </div>
        </div>

        <div v-if="filteredItems.length === 0" class="menu-empty">
          <span class="empty-icon">📭</span>
          <span class="empty-text">没有找到匹配的文件</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { debounce } from 'lodash-es';

// ============================================================================
// 类型定义
// ============================================================================

interface PathItem {
  name: string;           // 文件/文件夹名
  path: string;           // 完整路径
  displayPath: string;    // 显示路径（相对路径）
  type: 'file' | 'folder';
  depth: number;          // 深度（用于缩进）
}

interface PathAutocompleteProps {
  triggerChar?: string;   // 触发字符，默认 '@'
  inputElement?: HTMLElement | null;  // 输入框元素
  workspaceRoot?: string; // 工作区根目录
  maxItems?: number;      // 最大显示项数
}

const props = withDefaults(defineProps<PathAutocompleteProps>(), {
  triggerChar: '@',
  inputElement: null,
  workspaceRoot: '',
  maxItems: 10
});

// ============================================================================
// 状态管理
// ============================================================================

const showMenu = ref(false);
const items = ref<PathItem[]>([]);
const selectedIndex = ref(0);
const searchQuery = ref('');
const currentPosition = ref({ x: 0, y: 0 });
const containerRef = ref<HTMLElement>();

// ============================================================================
// 计算属性
// ============================================================================

const menuTitle = computed(() => {
  if (!searchQuery.value) return '文件路径';
  if (searchQuery.value.includes('*')) return '通配符搜索';
  return '文件路径';
});

const menuStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${currentPosition.value.x}px`,
  top: `${currentPosition.value.y}px`,
  zIndex: 9999
}));

const filteredItems = computed(() => {
  if (!searchQuery.value) {
    return items.value.slice(0, props.maxItems);
  }

  const query = searchQuery.value.toLowerCase();
  return items.value
    .filter(item => item.name.toLowerCase().includes(query))
    .slice(0, props.maxItems);
});

// ============================================================================
// 文件系统访问
// ============================================================================

/**
 * 获取工作区文件列表
 */
async function fetchWorkspaceFiles(): Promise<void> {
  try {
    // TODO: 实现真实的文件系统 API 调用
    // 这里需要后端提供一个 API 端点来列出工作区文件
    // const response = await fetch('/api/files/list');
    // const data = await response.json();

    // 模拟数据（开发测试用）
    items.value = [
      { name: 'src', path: '/src', displayPath: 'src/', type: 'folder', depth: 0 },
      { name: 'components', path: '/src/components', displayPath: 'src/components/', type: 'folder', depth: 1 },
      { name: 'ChatInput.vue', path: '/src/components/ChatInput.vue', displayPath: 'src/components/ChatInput.vue', type: 'file', depth: 2 },
      { name: 'services', path: '/src/services', displayPath: 'src/services/', type: 'folder', depth: 1 },
      { name: 'api.ts', path: '/src/services/api.ts', displayPath: 'src/services/api.ts', type: 'file', depth: 2 },
      { name: 'patent_agent.py', path: '/patent_agent.py', displayPath: 'patent_agent.py', type: 'file', depth: 0 },
      { name: 'context_manager.py', path: '/context_manager.py', displayPath: 'context_manager.py', type: 'file', depth: 0 },
      { name: 'README.md', path: '/README.md', displayPath: 'README.md', type: 'file', depth: 0 },
    ];
  } catch (error) {
    console.error('Failed to fetch workspace files:', error);
    items.value = [];
  }
}

/**
 * 递归搜索目录
 */
 
async function searchDirectory(_path: string): Promise<PathItem[]> {
  // TODO: 实现真实的目录搜索 API
  return [];
}

// ============================================================================
// UI 交互
// ============================================================================

/**
 * 获取文件图标
 */
function getItemIcon(item: PathItem): string {
  if (item.type === 'folder') return '📁';
  if (item.name.endsWith('.py')) return '🐍';
  if (item.name.endsWith('.vue')) return '💚';
  if (item.name.endsWith('.ts')) return '📘';
  if (item.name.endsWith('.js')) return '📜';
  if (item.name.endsWith('.md')) return '📝';
  if (item.name.endsWith('.json')) return '📋';
  return '📄';
}

/**
 * 选择项目
 */
function selectItem(index: number) {
  if (index < 0 || index >= filteredItems.value.length) return;

  const item = filteredItems.value[index];
  const insertText = props.triggerChar + item.displayPath;

  // 触发自定义事件，通知父组件插入文本
  emit('select', {
    text: insertText,
    path: item.path,
    type: item.type
  });

  hideMenu();
}

/**
 * 显示菜单
 */
function showMenuAt(x: number, y: number) {
  currentPosition.value = { x, y };
  showMenu.value = true;
  selectedIndex.value = 0;
}

/**
 * 隐藏菜单
 */
function hideMenu() {
  showMenu.value = false;
  searchQuery.value = '';
}

/**
 * 处理键盘导航
 */
function handleKeyNavigation(event: KeyboardEvent) {
  if (!showMenu.value) return;

  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault();
      selectedIndex.value = (selectedIndex.value + 1) % filteredItems.value.length;
      break;
    case 'ArrowUp':
      event.preventDefault();
      selectedIndex.value =
        (selectedIndex.value - 1 + filteredItems.value.length) % filteredItems.value.length;
      break;
    case 'Enter':
      event.preventDefault();
      selectItem(selectedIndex.value);
      break;
    case 'Escape':
      event.preventDefault();
      hideMenu();
      break;
    case 'Tab':
      event.preventDefault();
      // 自动补全到第一个匹配项
      if (filteredItems.value.length > 0) {
        selectItem(selectedIndex.value);
      }
      break;
  }
}

/**
 * 更新搜索查询
 */
const updateSearch = debounce((query: string) => {
  searchQuery.value = query;
}, 150);

// ============================================================================
// 公开方法
// ============================================================================

/**
 * 检查并触发自动补全
 */
async function checkTrigger(text: string, cursorPosition: number): Promise<boolean> {
  // 查找最近的 @ 符号
  const textBeforeCursor = text.substring(0, cursorPosition);
  const triggerIndex = textBeforeCursor.lastIndexOf(props.triggerChar);

  if (triggerIndex === -1) {
    hideMenu();
    return false;
  }

  // 提取 @ 后的路径
  const pathAfterTrigger = textBeforeCursor.substring(triggerIndex + 1);

  // 如果 @ 后面有空格，则不触发
  if (/\s/.test(pathAfterTrigger.substring(0, 1))) {
    hideMenu();
    return false;
  }

  // 获取光标位置用于显示菜单
  const rect = props.inputElement?.getBoundingClientRect();
  if (!rect) {
    hideMenu();
    return false;
  }

  // 显示菜单
  if (!showMenu.value) {
    // 初次显示，加载文件列表
    await fetchWorkspaceFiles();
    showMenuAt(rect.left, rect.bottom + 5);
  }

  // 更新搜索查询
  updateSearch(pathAfterTrigger);

  return true;
}

// ============================================================================
// 生命周期
// ============================================================================

onMounted(() => {
  // 添加全局键盘监听
  document.addEventListener('keydown', handleKeyNavigation);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyNavigation);
});

// ============================================================================
// 事件定义
// ============================================================================

const emit = defineEmits<{
  select: [value: { text: string; path: string; type: string }];
}>();

// 暴露方法给父组件
defineExpose({
  checkTrigger,
  hideMenu
});
</script>

<style scoped>
.path-autocomplete {
  position: relative;
}

.autocomplete-menu {
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 300px;
  max-width: 500px;
  max-height: 400px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.menu-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
}

.menu-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.menu-hint {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.menu-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 13px;
}

.menu-item:hover,
.menu-item.active {
  background: var(--el-color-primary-light-9);
}

.menu-item.active {
  border-left: 3px solid var(--el-color-primary);
  padding-left: 9px;
}

.item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.item-name {
  flex: 1;
  color: var(--el-text-color-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-suffix {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.item-path {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  color: var(--el-text-color-placeholder);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-text {
  font-size: 13px;
}

/* 动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* 滚动条样式 */
.menu-list::-webkit-scrollbar {
  width: 6px;
}

.menu-list::-webkit-scrollbar-track {
  background: transparent;
}

.menu-list::-webkit-scrollbar-thumb {
  background: var(--el-border-color-darker);
  border-radius: 3px;
}

.menu-list::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-dark);
}
</style>
