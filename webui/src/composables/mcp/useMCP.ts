import { ref, onMounted } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { MCPServer } from '@/types/mcp';

export function useMCP(workspaceId: string) {
  const mcpServerList = ref<MCPServer[]>([]);
  const loadingMCP = ref(false);

  // 加载MCP服务器列表
  const loadMCPServers = async () => {
    if (!workspaceId) return;

    loadingMCP.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getMCPServers(workspaceId);
      mcpServerList.value = response.servers || [];
    } catch (error: unknown) {
      ElMessage.error('加载MCP服务器列表失败');
      console.error('Failed to load MCP servers:', error);
    } finally {
      loadingMCP.value = false;
    }
  };

  // 显示创建MCP服务器对话框
  const showCreateMcpDialog = () => {
    ElMessage.info('创建MCP服务器功能开发中...');
  };

  // 编辑MCP服务器
  const editMcpServer = (server: MCPServer) => {
    ElMessage.info(`编辑MCP服务器 "${server.name}" 功能开发中...`);
  };

  // 删除MCP服务器
  const deleteMcpServer = async (serverName: string) => {
    if (!workspaceId) return;

    try {
      await ElMessageBox.confirm(
        `确定要删除MCP服务器 "${serverName}" 吗？此操作不可恢复。`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      await apiManager.getWorkspacesApi().deleteMCPServer(workspaceId, serverName);
      ElMessage.success('MCP服务器删除成功');
      await loadMCPServers();
    } catch (error: unknown) {
      if (error !== 'cancel') {
        const err = error as { response?: { data?: { detail?: string } } };
        ElMessage.error(err.response?.data?.detail || '删除失败');
        console.error('Failed to delete MCP server:', error);
      }
    }
  };

  // 测试MCP服务器连接
  const testMcpServer = async (serverName: string) => {
    ElMessage.info(`测试MCP服务器 "${serverName}" 连接功能开发中...`);
  };

  return {
    mcpServerList,
    loadingMCP,
    loadMCPServers,
    showCreateMcpDialog,
    editMcpServer,
    deleteMcpServer,
    testMcpServer
  };
}
