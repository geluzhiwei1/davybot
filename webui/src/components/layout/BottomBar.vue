/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-footer class="bottom-bar">
    <div class="left-controls">
      Agent：
      <el-dropdown @command="selectMode" placement="top">
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
      <el-dropdown @command="selectLLM" placement="top">
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

      <!-- 知识库选择器 -->
      <el-dropdown @command="toggleKnowledgeBase" :disabled="loadingKnowledgeBases" placement="top">
        <el-button>
          <el-icon>
            <Reading />
          </el-icon>
          {{ getKnowledgeBaseDisplayText() }}
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="base in knowledgeBases" :key="base.id" :command="base">
              <div class="kb-dropdown-item">
                <el-checkbox :model-value="selectedKnowledgeBases.includes(base.id)"
                  @change="() => toggleKnowledgeBase(base)" @click.stop>
                  {{ base.name }}
                </el-checkbox>
                <div class="kb-meta">
                  <el-tag v-if="base.is_default" type="success" size="small">默认</el-tag>
                  <el-tag size="small" type="info">{{ base.stats.total_documents }}</el-tag>
                </div>
              </div>
            </el-dropdown-item>
            <el-dropdown-item divided :disabled="true">
              <div class="kb-footer">
                <el-button text @click="handleOpenKnowledgeDrawer" size="small">
                  <el-icon>
                    <Setting />
                  </el-icon>
                  管理
                </el-button>
                <el-button text @click="loadKnowledgeBases" size="small" :loading="loadingKnowledgeBases">
                  <el-icon>
                    <Refresh />
                  </el-icon>
                  刷新
                </el-button>
              </div>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-button @click="refreshConfig" :loading="refreshing" :icon="Refresh" circle title="重新加载Agent和LLM配置" />
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
import { ElFooter, ElDropdown, ElDropdownMenu, ElDropdownItem, ElButton, ElIcon, ElMessage, ElCheckbox, ElTag, ElSwitch, ElTooltip } from 'element-plus';
import { ArrowDown, Cpu, Reading, Refresh, Setting } from '@element-plus/icons-vue';
import { workspacesApi } from '@/services/api';
import { knowledgeBasesApi } from '@/services/api/knowledge';
import { httpClient } from '@/services/api/http';
import type { KnowledgeBase } from '@/types/knowledge';

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

// 知识库选择
const selectedKnowledgeBases = ref<string[]>([]);
const knowledgeBases = ref<KnowledgeBase[]>([]);
const loadingKnowledgeBases = ref(false);

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
const refreshing = ref(false);
const route = useRoute();
const chatStore = useChatStore();

// 获取工作区ID的辅助函数
const getWorkspaceId = (): string => {
  return route.params.workspaceId as string;
};

// 获取Modes配置
const fetchModes = async (forceReload = false) => {
  const workspaceId = getWorkspaceId();
  if (!workspaceId) {
    console.error('Workspace ID is not available in the route.');
    return;
  }

  try {
    const reloadParam = forceReload ? '?reload=true' : '';
    const data = await httpClient.get<{ success: boolean; modes: Mode[] }>(
      `/workspaces/${workspaceId}/modes${reloadParam}`
    );
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

// 获取LLMs配置
const fetchLLMs = async (forceReload = false) => {
  const workspaceId = getWorkspaceId();
  if (!workspaceId) {
    console.error('Workspace ID is not available in the route.');
    return;
  }

  try {
    const reloadParam = forceReload ? '?reload=true' : '';
    const data = await httpClient.get<{ success: boolean; models: LLM[] }>(
      `/workspaces/${workspaceId}/llms${reloadParam}`
    );
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

onMounted(async () => {
  await Promise.all([fetchModes(), fetchLLMs(), loadKnowledgeBases()]);
});

const selectMode = async (mode: Mode) => {
  try {
    const workspaceId = route.params.workspaceId as string;
    await workspacesApi.updateUIContext(workspaceId, {
      current_mode: mode.slug
    });

    currentMode.value = mode;
    // 更新 chatStore 中的 uiContext
    chatStore.uiContext.currentMode = mode.slug;
  } catch (error) {
    console.error('Error updating mode:', error);
  }
};

const selectLLM = async (llm: LLM) => {
  try {
    const workspaceId = route.params.workspaceId as string;

    if (!workspaceId) {
      ElMessage.error('工作区ID不存在');
      return;
    }

    await workspacesApi.updateUIContext(workspaceId, {
      current_llm_id: llm.llm_id
    });

    currentLLM.value = llm;
    // 更新 chatStore 中的 uiContext
    chatStore.uiContext.currentLlmId = llm.llm_id;
  } catch (error) {
    ElMessage.error('切换 LLM 失败');
    console.error('Error switching LLM:', error);
  }
};

// 加载知识库列表
const loadKnowledgeBases = async () => {
  loadingKnowledgeBases.value = true;
  try {
    const response = await knowledgeBasesApi.listBases();
    knowledgeBases.value = response.items;
  } catch (error) {
    console.error('Failed to load knowledge bases:', error);
  } finally {
    loadingKnowledgeBases.value = false;
  }
};

// 处理知识库选择变化
const handleKnowledgeBasesChange = (baseIds: string[]) => {
  console.log('[BOTTOM_BAR] Selected knowledge bases:', baseIds);
  // 更新 chat store
  chatStore.selectedKnowledgeBaseIds = baseIds;
};

// 获取知识库显示文本
const getKnowledgeBaseDisplayText = (): string => {
  if (selectedKnowledgeBases.value.length === 0) {
    return '知识库';
  } else if (selectedKnowledgeBases.value.length === 1) {
    const base = knowledgeBases.value.find(b => b.id === selectedKnowledgeBases.value[0]);
    return base ? base.name : '知识库';
  } else {
    return `知识库 (${selectedKnowledgeBases.value.length})`;
  }
};

// 切换知识库选择状态
const toggleKnowledgeBase = (base: KnowledgeBase) => {
  console.log('[BOTTOM_BAR] toggleKnowledgeBase called with:', {
    'base.id': base.id,
    'base.id type': typeof base.id,
    'base.id length': base.id.length,
    'base.name': base.name
  });

  const index = selectedKnowledgeBases.value.indexOf(base.id);
  if (index > -1) {
    // 已选中，移除
    selectedKnowledgeBases.value.splice(index, 1);
  } else {
    // 未选中，添加
    selectedKnowledgeBases.value.push(base.id);
    console.log('[BOTTOM_BAR] Added base.id to selectedKnowledgeBases:', base.id);
  }
  // 【修复】更新 chat store，确保 ChatArea 能读取到选择的知识库
  chatStore.selectedKnowledgeBaseIds = [...selectedKnowledgeBases.value];
  console.log('[BOTTOM_BAR] Updated chatStore.selectedKnowledgeBaseIds:', chatStore.selectedKnowledgeBaseIds);
  console.log('[BOTTOM_BAR] Verification - First ID length:', chatStore.selectedKnowledgeBaseIds[0]?.length);
};

// 打开知识库管理抽屉
const handleOpenKnowledgeDrawer = () => {
  // 触发打开知识库管理面板的事件
  window.dispatchEvent(new CustomEvent('open-knowledge-drawer'));
};

const refreshConfig = async () => {
  if (refreshing.value) return;

  refreshing.value = true;
  try {
    const workspaceId = route.params.workspaceId as string;
    if (!workspaceId) {
      ElMessage.error('工作区ID不存在');
      console.error('Workspace ID is missing:', route.params);
      return;
    }

    // 重新获取Modes和LLMs (强制重新加载)
    await Promise.all([fetchModes(true), fetchLLMs()]);
    ElMessage.success('配置已刷新');
  } catch (error) {
    console.error('Error refreshing config:', error);
    ElMessage.error('刷新配置时发生错误');
  } finally {
    refreshing.value = false;
  }
};
</script>

<style scoped>
.bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background-color: var(--el-bg-color-page);
  border-top: 1px solid var(--el-border-color-lighter);
  height: 60px;
  box-sizing: border-box;
}

.left-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  overflow-x: auto;
}

.right-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mode-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.mode-item:hover {
  background-color: var(--el-bg-color);
}

.mode-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.mode-info {
  flex: 1;
  min-width: 0;
}

.mode-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.mode-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.mode-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-tag-system {
  background-color: #e7f5ff;
  color: #0050b3;
  border-color: #91caff;
}

.source-tag-user {
  background-color: #f6ffed;
  color: #389e0d;
  border-color: #b7eb8f;
}

.source-tag-workspace {
  background-color: #fff7e6;
  color: #d46b08;
  border-color: #ffd591;
}

.llm-model-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}

/* 知识库选择器样式 */
.kb-selector-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.kb-selector-inline {
  width: 300px;
  max-width: 300px;
}

.kb-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}

.kb-name {
  flex: 1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.kb-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.kb-dropdown-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 4px 0;
}

.kb-dropdown-item .el-checkbox {
  width: 100%;
  margin: 0;
}

/* 标签折叠优化 */
.kb-selector-inline :deep(.el-select__tags) {
  max-width: calc(100% - 32px);
}

.kb-selector-inline :deep(.el-tag) {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .bottom-bar {
    padding: 8px;
  }

  .left-controls {
    gap: 8px;
  }

  .kb-selector-inline {
    width: 200px;
    max-width: 200px;
  }

  .kb-selector-label {
    display: none;
    /* 移动端隐藏标签 */
  }
}
</style>