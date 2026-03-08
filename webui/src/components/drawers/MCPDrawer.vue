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
      <el-table :data="mcpServerList" stripe style="width: 100%;" max-height="calc(100vh - 300px)">
        <el-table-column prop="name" label="名称" width="180" />

        <el-table-column prop="command" label="命令" show-overflow-tooltip>
          <template #default="scope">
            <code style="font-size: 12px;">{{ scope.row.command }}</code>
          </template>
        </el-table-column>

        <el-table-column prop="cwd" label="工作目录" width="180" show-overflow-tooltip />

        <el-table-column prop="timeout" label="超时(秒)" width="90" align="center">
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

        <el-table-column label="操作" width="220" fixed="right">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="editMcpServer(scope.row)">
              编辑
            </el-button>
            <el-button link type="success" size="small" @click="testMcpServer(scope.row.name)">
              测试
            </el-button>
            <el-button link type="danger" size="small" @click="deleteMcpServer(scope.row.name)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loadingMCP && mcpServerList.length === 0" description="暂无MCP服务器配置" style="margin-top: 40px;">
        <el-button type="primary" @click="showCreateMcpDialog">添加第一个服务器</el-button>
      </el-empty>

      <!-- MCP Server 编辑/创建对话框 -->
      <el-dialog
        v-model="showMcpDialog"
        :title="editingMcpServer ? '编辑MCP服务器' : '添加MCP服务器'"
        width="700px"
        :close-on-click-modal="false"
      >
        <el-form :model="mcpForm" label-width="120px">
          <el-form-item label="服务器名称" required>
            <el-input
              v-model="mcpForm.name"
              placeholder="MCP服务器名称（唯一标识）"
              :disabled="!!editingMcpServer"
            />
          </el-form-item>

          <el-form-item label="命令" required>
            <el-input v-model="mcpForm.command" placeholder="例如: npx, uvx, python" />
          </el-form-item>

          <el-form-item label="参数">
            <el-input
              v-model="mcpForm.argsText"
              type="textarea"
              :rows="3"
              placeholder="每行一个参数，例如：&#10;-y&#10;@modelcontextprotocol/server-filesystem"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              每行一个参数
            </div>
          </el-form-item>

          <el-form-item label="工作目录">
            <el-input v-model="mcpForm.cwd" placeholder="可选，默认为当前工作目录" />
          </el-form-item>

          <el-form-item label="超时时间">
            <el-input-number
              v-model="mcpForm.timeout"
              :min="10"
              :max="600"
              :step="10"
              style="width: 100%;"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              秒（默认300秒）
            </div>
          </el-form-item>

          <el-form-item label="自动允许工具">
            <el-input
              v-model="mcpForm.alwaysAllowText"
              type="textarea"
              :rows="3"
              placeholder="每行一个工具名称，这些工具将自动授权无需确认"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              每行一个工具名称
            </div>
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="showMcpDialog = false">取消</el-button>
          <el-button type="primary" @click="saveMcpServer" :loading="savingMcp">
            {{ editingMcpServer ? '更新' : '创建' }}
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
import { watch, onMounted } from 'vue';
import { useMCP } from '@/composables/mcp/useMCP';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  mcpServerList,
  loadingMCP,
  loadMCPServers,
  showMcpDialog,
  showCreateMcpDialog,
  editMcpServer,
  saveMcpServer,
  deleteMcpServer,
  testMcpServer,
  mcpForm,
  savingMcp,
  editingMcpServer
} = useMCP(props.workspaceId);

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

code {
  background-color: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.9em;
}
</style>
