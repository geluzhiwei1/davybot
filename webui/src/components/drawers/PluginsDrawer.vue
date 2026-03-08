<template>
  <div class="plugins-drawer">
    <div class="drawer-content">
      <el-alert title="插件管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区插件。插件可以扩展Dawei的功能，添加新的工具和能力。
          </p>
        </template>
      </el-alert>

      <!-- Use PluginConfigPanel component -->
      <PluginConfigPanel
        v-if="workspaceId"
        :workspace-id="workspaceId"
        :can-edit="true"
        @open-market="handleOpenMarket"
      />

      <!-- Fallback when no workspace -->
      <el-alert v-else title="未选择工作区" type="warning" :closable="false" show-icon>
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            请先选择一个工作区以管理插件。
          </p>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import PluginConfigPanel from '@/components/workspace/PluginConfigPanel.vue';

const props = defineProps<{
  workspaceId?: string;
}>();

const handleOpenMarket = (type: 'plugin' | 'skill' | 'agent') => {
  console.log('Open market for:', type);
  // 可以在这里触发打开市场对话框
};
</script>

<style scoped>
.plugins-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
  height: 100%;
}
</style>
