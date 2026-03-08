<template>
  <div class="mcp-drawer">
    <div class="drawer-content" v-loading="loadingMCP">
      <!-- Header -->
      <el-alert title="MCP服务器管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理Model Context Protocol (MCP) 服务器连接。MCP服务器可以为AI代理提供额外的工具和资源。
          </p>
        </template>
      </el-alert>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">已配置的服务器 ({{ mcpServerList.length }})</span>
        <el-button type="primary" size="small" @click="showCreateMcpDialog">
          <el-icon><Plus /></el-icon>
          添加服务器
        </el-button>
      </div>

      <!-- MCP Servers Table -->
      <el-table :data="mcpServerList" stripe style="width: 100%;">
        <el-table-column prop="name" label="名称" width="200" />

        <el-table-column prop="command" label="命令" show-overflow-tooltip>
          <template #default="scope">
            <code style="font-size: 12px;">{{ scope.row.command }}</code>
          </template>
        </el-table-column>

        <el-table-column prop="cwd" label="工作目录" width="200" show-overflow-tooltip />

        <el-table-column prop="timeout" label="超时(秒)" width="100" align="center">
          <template #default="scope">
            {{ scope.row.timeout || 30 }}
          </template>
        </el-table-column>

        <el-table-column label="状态" width="80" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.disabled ? 'danger' : 'success'" size="small">
              {{ scope.row.disabled ? '禁用' : '启用' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="editMcpServer(scope.row)">编辑</el-button>
            <el-button size="small" type="info" @click="testMcpServer(scope.row.name)">测试</el-button>
            <el-button size="small" type="danger" @click="deleteMcpServer(scope.row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loadingMCP && mcpServerList.length === 0" description="暂无MCP服务器配置" style="margin-top: 40px;">
        <el-button type="primary" @click="showCreateMcpDialog">添加第一个服务器</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import { onMounted, watch } from 'vue';
import { useMCP } from '@/composables/mcp/useMCP';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  mcpServerList,
  loadingMCP,
  loadMCPServers,
  showCreateMcpDialog,
  editMcpServer,
  deleteMcpServer,
  testMcpServer
} = useMCP(props.workspaceId || '');

onMounted(() => {
  if (props.workspaceId) {
    loadMCPServers();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadMCPServers();
  }
});
</script>

<style scoped>
.mcp-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
