/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-footer class="bottom-bar">
    <div class="left-controls">
      Agent：
      <el-dropdown @command="selectMode">
        <el-button>
          <span v-if="currentMode">{{ getModeIcon(currentMode) }} {{ getModeDisplayName(currentMode) }}</span>
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="mode in modes" :key="mode.slug" :command="mode">
              <div class="mode-item">
                <span class="mode-icon">{{ getModeIcon(mode) }}</span>
                <div class="mode-info">
                  <div class="mode-name-row">
                    <span class="mode-name">{{ getModeDisplayName(mode) }}</span>
                    <el-tag v-if="mode.source" :size="'small'" :effect="'plain'" :class="`source-tag-${mode.source}`">
                      {{ mode.source }}
                    </el-tag>
                  </div>
                  <div class="mode-description">{{ mode.description }}</div>
                </div>
                <el-tag v-if="mode.is_default" size="small" type="primary" effect="light">默认</el-tag>
              </div>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      LLM:
      <el-dropdown @command="selectLLM">
        <el-button>
          <el-icon>
            <Cpu />
          </el-icon>
          {{ currentLLM?.llm_id }}
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="llm in llms" :key="llm.llm_id" :command="llm">
              {{ llm.llm_id }} <span class="llm-model-id">({{ llm.model_id }})</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="right-controls">
      <!-- <el-switch v-model="autoApprove" @change="toggleAutoApprove" active-text="自动审批" /> -->
    </div>
  </el-footer>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import { ElFooter, ElDropdown, ElDropdownMenu, ElDropdownItem, ElButton, ElIcon, ElMessage } from 'element-plus';
import { ArrowDown, Cpu } from '@element-plus/icons-vue';

interface Mode {
  slug: string;
  name: string;
  description: string;
  is_default?: boolean;
  icon?: string;
  source?: 'system' | 'user' | 'workspace';
}

interface LLM {
  llm_id: string;
  model_id: string;
}

const currentMode = ref<Mode | null>(null);
const modes = ref<Mode[]>([]);

// 从mode name中提取emoji和display name
const getModeIcon = (mode: Mode): string => {
  if (mode.icon) return mode.icon;

  // 从name开头提取emoji (简单判断: 检查第一个字符的Unicode码点)
  const firstChar = mode.name.charAt(0);
  const codePoint = mode.name.codePointAt(0) || 0;

  // emoji范围检查
  const isEmoji = (
    (codePoint >= 0x1F300 && codePoint <= 0x1F5FF) ||  // Misc Symbols
    (codePoint >= 0x1F900 && codePoint <= 0x1F9FF) ||  // Supplemental Symbols
    (codePoint >= 0x1F600 && codePoint <= 0x1F64F) ||  // Emoticons
    (codePoint >= 0x1F680 && codePoint <= 0x1F6FF) ||  // Transport
    (codePoint >= 0x2600 && codePoint <= 0x27BF) ||    // Dingbats
    (codePoint >= 0x2700 && codePoint <= 0x27BF) ||    // Dingbats
    (codePoint >= 0x1F300 && codePoint <= 0x1F9FF) ||   // Symbols
    (codePoint >= 0x2300 && codePoint <= 0x23FF) ||    // Technical
    (codePoint >= 0x2B00 && codePoint <= 0x2BFF)       // Arrows
  );

  if (isEmoji) {
    // emoji可能由多个字符组成 (代理对)
    const emoji = mode.name.match(/^[\uD800-\uDFFF].|^\S+/u);
    return emoji ? emoji[0] : firstChar;
  }

  return '';
};

const getModeDisplayName = (mode: Mode): string => {
  if (mode.icon) return mode.name;

  // 从name开头移除emoji
  const icon = getModeIcon(mode);
  if (icon) {
    const displayName = mode.name.substring(icon.length).trim();
    return displayName || mode.name;
  }
  return mode.name;
};
const currentLLM = ref<LLM | null>(null);
const llms = ref<LLM[]>([]);
const route = useRoute();
const chatStore = useChatStore();

onMounted(async () => {
  const workspaceId = route.params.workspaceId as string;
  if (!workspaceId) {
    console.error('Workspace ID is not available in the route.');
    return;
  }

  const fetchModes = async () => {
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/modes`);
      const data = await response.json();
      if (data.success && Array.isArray(data.modes)) {
        modes.value = data.modes;
        currentMode.value = data.modes.find((m: Mode) => m.is_default) || data.modes[0];
        // 同步到chatStore
        if (currentMode.value) {
          chatStore.uiContext.currentMode = currentMode.value.slug;
        }
      }
    } catch (error) {
      console.error('Error fetching modes:', error);
    }
  };

  const fetchLLMs = async () => {
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/llms`);
      const data = await response.json();
      if (data.success && Array.isArray(data.models)) {
        llms.value = data.models;
        currentLLM.value = data.models[0];
        // 同步到chatStore
        if (currentLLM.value) {
          chatStore.uiContext.currentLlmId = currentLLM.value.llm_id;
        }
      }
    } catch (error) {
      console.error('Error fetching LLMs:', error);
    }
  };

  await Promise.all([fetchModes(), fetchLLMs()]);
});

const selectMode = async (mode: Mode) => {
  try {
    const workspaceId = route.params.workspaceId as string;
    const response = await fetch(`/api/workspaces/${workspaceId}/ui/context`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        context: {
          current_mode: mode.slug
        }
      })
    });

    if (response.ok) {
      currentMode.value = mode;
      // 更新 chatStore 中的 uiContext
      chatStore.uiContext.currentMode = mode.slug;
    } else {
      console.error('Failed to update mode, status:', response.status);
    }
  } catch (error) {
    console.error('Error updating mode:', error);
  }
};

const selectLLM = async (llm: LLM) => {
  try {
    const workspaceId = route.params.workspaceId as string;

    if (!workspaceId) {
      ElMessage.error('工作区ID不存在');
      console.error('Workspace ID is missing:', route.params);
      return;
    }

    const url = `/api/workspaces/${workspaceId}/ui/context`;

    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        current_llm_id: llm.llm_id
      })
    });

    if (response.ok) {
      currentLLM.value = llm;
      // 更新 chatStore 中的 uiContext
      chatStore.uiContext.currentLlmId = llm.llm_id;
      ElMessage.success('LLM 已更新');
    } else {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('Failed to update LLM:', response.status, errorData);
      // 显示错误提示给用户
      ElMessage.error(`更新LLM失败 (${response.status}): ${errorData.detail || response.statusText}`);
    }
  } catch (error) {
    console.error('Error updating LLM:', error);
    ElMessage.error('更新LLM时发生网络错误');
  }
};
</script>

<style scoped>
.bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 16px;
  background-color: var(--el-bg-color-overlay);
  border-top: 1px solid var(--el-border-color-light);
}

.left-controls,
.right-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 下拉菜单项样式优化 */
:deep(.el-dropdown-menu__item) {
  padding: 8px 12px;
  line-height: 1.5;
  min-height: 56px;
}

:deep(.el-dropdown-menu__item:hover) {
  background-color: var(--el-fill-color-light);
}

.mode-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.mode-icon {
  font-size: 20px;
  line-height: 1;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mode-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mode-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.mode-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  line-height: 1.4;
}

.mode-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

/* Source 标签样式 */
:deep(.el-tag.source-tag-system) {
  background-color: var(--el-color-info-light-9);
  border-color: var(--el-color-info-light-7);
  color: var(--el-color-info);
  font-size: 11px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-weight: 500;
}

:deep(.el-tag.source-tag-user) {
  background-color: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-7);
  color: var(--el-color-success);
  font-size: 11px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-weight: 500;
}

:deep(.el-tag.source-tag-workspace) {
  background-color: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning-light-7);
  color: var(--el-color-warning);
  font-size: 11px;
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-weight: 500;
}

/* 默认标签优化 */
:deep(.el-dropdown-menu__item .el-tag) {
  flex-shrink: 0;
}

.llm-model-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}
</style>