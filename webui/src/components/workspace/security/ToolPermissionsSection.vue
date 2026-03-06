<template>
  <div class="tool-permissions-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 用户级：基础允许的工具组 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.toolPermissions.baseAllowedGroups')"
      >
        <el-checkbox-group
          v-model="baseAllowedGroups"
          @change="handleGroupsUpdate"
        >
          <el-checkbox value="read">📖 Read</el-checkbox>
          <el-checkbox value="edit">✏️ Edit</el-checkbox>
          <el-checkbox value="browser">🌐 Browser</el-checkbox>
          <el-checkbox value="command">💻 Command</el-checkbox>
          <el-checkbox value="mcp">🔌 MCP</el-checkbox>
          <el-checkbox value="task_graph">📊 Task Graph</el-checkbox>
          <el-checkbox value="workflow">🔄 Workflow</el-checkbox>
        </el-checkbox-group>
        <span class="form-item-help">
          {{ t('workspace.settings.security.toolPermissions.baseAllowedGroupsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：允许的工具组 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.toolPermissions.allowedGroups')"
      >
        <el-checkbox-group
          v-model="allowedGroups"
          @change="handleGroupsUpdate"
        >
          <el-checkbox value="read">📖 Read</el-checkbox>
          <el-checkbox value="edit">✏️ Edit</el-checkbox>
          <el-checkbox value="browser">🌐 Browser</el-checkbox>
          <el-checkbox value="command">💻 Command</el-checkbox>
          <el-checkbox value="mcp">🔌 MCP</el-checkbox>
          <el-checkbox value="task_graph">📊 Task Graph</el-checkbox>
          <el-checkbox value="workflow">🔄 Workflow</el-checkbox>
        </el-checkbox-group>
        <span class="form-item-help">
          {{ t('workspace.settings.security.toolPermissions.allowedGroupsHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：基础拒绝的工具组 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.toolPermissions.baseDeniedGroups')"
      >
        <el-checkbox-group
          v-model="baseDeniedGroups"
          @change="handleGroupsUpdate"
        >
          <el-checkbox value="read">📖 Read</el-checkbox>
          <el-checkbox value="edit">✏️ Edit</el-checkbox>
          <el-checkbox value="browser">🌐 Browser</el-checkbox>
          <el-checkbox value="command">💻 Command</el-checkbox>
          <el-checkbox value="mcp">🔌 MCP</el-checkbox>
          <el-checkbox value="task_graph">📊 Task Graph</el-checkbox>
          <el-checkbox value="workflow">🔄 Workflow</el-checkbox>
        </el-checkbox-group>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.toolPermissions.baseDeniedGroupsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：拒绝的工具组 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.toolPermissions.deniedGroups')"
      >
        <el-checkbox-group
          v-model="deniedGroups"
          @change="handleGroupsUpdate"
        >
          <el-checkbox value="read">📖 Read</el-checkbox>
          <el-checkbox value="edit">✏️ Edit</el-checkbox>
          <el-checkbox value="browser">🌐 Browser</el-checkbox>
          <el-checkbox value="command">💻 Command</el-checkbox>
          <el-checkbox value="mcp">🔌 MCP</el-checkbox>
          <el-checkbox value="task_graph">📊 Task Graph</el-checkbox>
          <el-checkbox value="workflow">🔄 Workflow</el-checkbox>
        </el-checkbox-group>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.toolPermissions.deniedGroupsHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：基础允许的具体工具 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.toolPermissions.baseAllowedTools')"
      >
        <el-select
          v-model="baseAllowedTools"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.toolPermissions.toolsPlaceholder')"
          @change="handleToolsUpdate"
        >
          <el-option
            v-for="tool in commonTools"
            :key="tool"
            :label="tool"
            :value="tool"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.toolPermissions.baseAllowedToolsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：允许的具体工具 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.toolPermissions.allowedTools')"
      >
        <el-select
          v-model="allowedTools"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.toolPermissions.toolsPlaceholder')"
          @change="handleToolsUpdate"
        >
          <el-option
            v-for="tool in commonTools"
            :key="tool"
            :label="tool"
            :value="tool"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.toolPermissions.allowedToolsHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：基础拒绝的具体工具 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.toolPermissions.baseDeniedTools')"
      >
        <el-select
          v-model="baseDeniedTools"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.toolPermissions.toolsPlaceholder')"
          @change="handleToolsUpdate"
        >
          <el-option
            v-for="tool in dangerousTools"
            :key="tool"
            :label="tool"
            :value="tool"
          />
        </el-select>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.toolPermissions.baseDeniedToolsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：拒绝的具体工具 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.toolPermissions.deniedTools')"
      >
        <el-select
          v-model="deniedTools"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.toolPermissions.toolsPlaceholder')"
          @change="handleToolsUpdate"
        >
          <el-option
            v-for="tool in dangerousTools"
            :key="tool"
            :label="tool"
            :value="tool"
          />
        </el-select>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.toolPermissions.deniedToolsHelp') }}
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { UserSecuritySettings, WorkspaceSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  modelValue: UserSecuritySettings | WorkspaceSecuritySettings;
  isUserLevel?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: UserSecuritySettings | WorkspaceSecuritySettings];
}>();

const { t } = useI18n();
const localValue = ref<UserSecuritySettings | WorkspaceSecuritySettings>({ ...props.modelValue });

// 常见工具
const commonTools = [
  'read_file',
  'write_file',
  'list_files',
  'search_files',
  'directory_tree',
  'ask_followup_question',
  'attempt_completion',
  'switch_mode',
  'run_slash_command'
];

// 危险工具
const dangerousTools = [
  'execute_command',
  'execute_pip_command',
  'browser_execute',
  'delete_file',
  'move_file',
  'create_directory'
];

// 用户级：基础允许的工具组
const baseAllowedGroups = computed({
  get: () => (localValue.value as UserSecuritySettings).baseAllowedToolGroups,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseAllowedToolGroups = val;
  }
});

// 用户级：基础拒绝的工具组
const baseDeniedGroups = computed({
  get: () => (localValue.value as UserSecuritySettings).baseDeniedToolGroups,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseDeniedToolGroups = val;
  }
});

// 用户级：基础允许的具体工具
const baseAllowedTools = computed({
  get: () => (localValue.value as UserSecuritySettings).baseAllowedTools,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseAllowedTools = val;
  }
});

// 用户级：基础拒绝的具体工具
const baseDeniedTools = computed({
  get: () => (localValue.value as UserSecuritySettings).baseDeniedTools,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseDeniedTools = val;
  }
});

// 工作区级：允许的工具组
const allowedGroups = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).allowedToolGroups || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).allowedToolGroups = val;
  }
});

// 工作区级：拒绝的工具组
const deniedGroups = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).deniedToolGroups || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).deniedToolGroups = val;
  }
});

// 工作区级：允许的具体工具
const allowedTools = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).allowedTools || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).allowedTools = val;
  }
});

// 工作区级：拒绝的具体工具
const deniedTools = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).deniedTools || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).deniedTools = val;
  }
});

watch(
  () => props.modelValue,
  (newValue) => {
    localValue.value = { ...newValue };
  },
  { deep: true }
);

const handleUpdate = () => {
  emit('update:modelValue', localValue.value);
};

const handleGroupsUpdate = () => {
  handleUpdate();
};

const handleToolsUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.tool-permissions-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;

    &.warning {
      color: var(--el-color-warning);
      font-weight: 500;
    }
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }

  :deep(.el-checkbox-group) {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
