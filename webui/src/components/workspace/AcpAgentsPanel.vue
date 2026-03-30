/* eslint-disable */
<template>
  <div class="acp-agents-panel">
    <!-- Header -->
    <div class="panel-header">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            ACP (Agent Client Protocol) 兼容的外部 AI Agent。扫描系统 PATH 自动发现已安装的 Agent，也可手动添加。
          </p>
        </template>
      </el-alert>

      <div class="header-actions">
        <el-button type="primary" @click="scanAgents" :loading="scanning" :icon="Search">
          扫描发现
        </el-button>
        <el-button @click="showAddDialog = true" :icon="Plus">
          手动添加
        </el-button>
      </div>
    </div>

    <!-- Agent List -->
    <el-table :data="agents" style="width: 100%" v-loading="loading"
      empty-text="暂无注册的 ACP Agent，点击「扫描发现」开始">
      <el-table-column prop="command" label="命令" width="140">
        <template #default="{ row }">
          <code>{{ row.command }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.available && !row.disabled ? 'success' : row.disabled ? 'info' : 'danger'" size="small">
            {{ row.available && !row.disabled ? '可用' : row.disabled ? '已禁用' : '未安装' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.manual ? 'warning' : 'primary'" size="small">
            {{ row.manual ? '手动' : '扫描' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.available"
            :type="row.disabled ? 'success' : 'warning'"
            size="small"
            text
            @click="toggleEnabled(row)">
            {{ row.disabled ? '启用' : '禁用' }}
          </el-button>
          <el-button type="danger" size="small" text @click="removeAgent(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add Agent Dialog -->
    <el-dialog v-model="showAddDialog" title="手动添加 ACP Agent" width="480px" @close="resetAddForm">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="命令" required>
          <el-input v-model="addForm.command" placeholder="例如: codex" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            可执行文件名，必须在系统 PATH 中存在
          </div>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="addForm.name" placeholder="例如: Codex CLI" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="addForm.description" type="textarea" :rows="2"
            placeholder="Agent 功能描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addAgent" :loading="adding">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search, Plus } from '@element-plus/icons-vue';
import { acpAgentsApi } from '@/services/api/services/acpAgents';
import type { ACPAgentInfo } from '@/services/api/services/acpAgents';

const props = defineProps<{
  workspaceId: string;
}>();

const agents = ref<ACPAgentInfo[]>([]);
const loading = ref(false);
const scanning = ref(false);
const adding = ref(false);
const showAddDialog = ref(false);
const addForm = ref({
  command: '',
  name: '',
  description: ''
});

const loadAgents = async () => {
  if (!props.workspaceId) return;
  loading.value = true;
  try {
    const response = await acpAgentsApi.getAgents(props.workspaceId);
    agents.value = response.agents || [];
  } catch (error) {
    console.error('Failed to load ACP agents:', error);
  } finally {
    loading.value = false;
  }
};

const scanAgents = async () => {
  if (!props.workspaceId) return;
  scanning.value = true;
  try {
    const response = await acpAgentsApi.scanAgents(props.workspaceId);
    agents.value = response.agents || [];
    ElMessage.success(response.message || `发现 ${agents.value.length} 个 ACP Agent`);
  } catch (error) {
    ElMessage.error('扫描失败');
    console.error('Failed to scan ACP agents:', error);
  } finally {
    scanning.value = false;
  }
};

const addAgent = async () => {
  if (!props.workspaceId || !addForm.value.command) {
    ElMessage.warning('请输入命令名');
    return;
  }
  adding.value = true;
  try {
    await acpAgentsApi.addAgent(props.workspaceId, addForm.value);
    ElMessage.success(`Agent "${addForm.value.command}" 添加成功`);
    showAddDialog.value = false;
    resetAddForm();
    await loadAgents();
  } catch (error: unknown) {
    ElMessage.error(error?.response?.data?.detail || '添加失败');
    console.error('Failed to add ACP agent:', error);
  } finally {
    adding.value = false;
  }
};

const removeAgent = async (agent: ACPAgentInfo) => {
  if (!props.workspaceId) return;
  try {
    await ElMessageBox.confirm(
      `确定要删除 Agent "${agent.command}" 吗?`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    );
    await acpAgentsApi.removeAgent(props.workspaceId, agent.command);
    ElMessage.success(`Agent "${agent.command}" 已删除`);
    await loadAgents();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
      console.error('Failed to remove ACP agent:', error);
    }
  }
};

const toggleEnabled = async (agent: ACPAgentInfo) => {
  if (!props.workspaceId) return;
  const newDisabled = !agent.disabled;
  try {
    await acpAgentsApi.toggleAgent(props.workspaceId, agent.command, newDisabled);
    ElMessage.success(`Agent "${agent.command}" 已${newDisabled ? '禁用' : '启用'}`);
    await loadAgents();
  } catch (error) {
    ElMessage.error('操作失败');
    console.error('Failed to toggle ACP agent:', error);
  }
};

const resetAddForm = () => {
  addForm.value = { command: '', name: '', description: '' };
};

onMounted(() => {
  loadAgents();
});
</script>

<style scoped>
.acp-agents-panel {
  padding: 16px;
}

.panel-header {
  margin-bottom: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
