import { ref } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { MCPServer } from '@/types/mcp';

export function useMCP(workspaceId?: string) {
  const mcpServerList = ref<MCPServer[]>([]);
  const loadingMCP = ref(false);

  // MCP对话框相关
  const showMcpDialog = ref(false);
  const editingMcpServer = ref<string | null>(null);
  const mcpForm = ref({
    name: '',
    command: '',
    argsText: '',
    cwd: '',
    timeout: 300,
    alwaysAllowText: ''
  });
  const savingMcp = ref(false);

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
    editingMcpServer.value = null;
    resetMcpForm();
    showMcpDialog.value = true;
  };

  // 编辑MCP服务器
  const editMcpServer = (server: MCPServer) => {
    editingMcpServer.value = server.name;
    mcpForm.value = {
      name: server.name,
      command: server.command || '',
      argsText: (server.args || []).join('\n'),
      cwd: server.cwd || '',
      timeout: server.timeout || 300,
      alwaysAllowText: (server.always_allow || []).join('\n')
    };
    showMcpDialog.value = true;
  };

  // 验证MCP命令配置
  const validateMcpConfig = (): { valid: boolean; error?: string } => {
    if (!mcpForm.value.name.trim()) {
      return { valid: false, error: '服务器名称不能为空' };
    }

    if (!mcpForm.value.command.trim()) {
      return { valid: false, error: '命令不能为空' };
    }

    // 验证命令格式（基本的安全检查）
    const command = mcpForm.value.command.trim();
    if (command.includes('|') || command.includes(';') || command.includes('&') || command.includes('$(')) {
      return { valid: false, error: '命令包含非法字符（管道符、分号等）' };
    }

    // 验证超时时间
    if (mcpForm.value.timeout < 1 || mcpForm.value.timeout > 3600) {
      return { valid: false, error: '超时时间必须在1-3600秒之间' };
    }

    return { valid: true };
  };

  // 保存MCP服务器
  const saveMcpServer = async () => {
    if (!workspaceId) {
      ElMessage.warning('工作区ID不能为空');
      return;
    }

    // 验证表单
    const validation = validateMcpConfig();
    if (!validation.valid) {
      ElMessage.error(validation.error);
      return;
    }

    savingMcp.value = true;
    try {
      // 将文本按行分割为数组
      const args = mcpForm.value.argsText
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

      const alwaysAllow = mcpForm.value.alwaysAllowText
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

      const serverData = {
        name: mcpForm.value.name,
        command: mcpForm.value.command,
        args: args,
        cwd: mcpForm.value.cwd,
        timeout: mcpForm.value.timeout,
        always_allow: alwaysAllow,
        disabled: false
      };

      if (editingMcpServer.value) {
        // 更新
        await apiManager.getWorkspacesApi().updateMCPServer(
          workspaceId,
          editingMcpServer.value,
          serverData
        );
        ElMessage.success('MCP服务器更新成功');
      } else {
        // 创建
        await apiManager.getWorkspacesApi().createMCPServer(workspaceId, serverData);
        ElMessage.success('MCP服务器创建成功');
      }

      showMcpDialog.value = false;
      await loadMCPServers();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '保存失败');
      console.error('Failed to save MCP server:', error);
    } finally {
      savingMcp.value = false;
    }
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
    if (!workspaceId) return;

    try {
      ElMessage.info(`正在测试MCP服务器 "${serverName}" 连接...`);
      const response = await apiManager.getWorkspacesApi().testMCPServer(workspaceId, serverName);

      if (response.success) {
        ElMessage.success('MCP服务器连接测试成功');
      } else {
        ElMessage.error('MCP服务器连接测试失败');
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '连接测试失败');
      console.error('Failed to test MCP server:', error);
    }
  };

  // 重置MCP表单
  const resetMcpForm = () => {
    mcpForm.value = {
      name: '',
      command: '',
      argsText: '',
      cwd: '',
      timeout: 300,
      alwaysAllowText: ''
    };
  };

  return {
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
  };
}
