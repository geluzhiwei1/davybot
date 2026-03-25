import { ref } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { Agent } from '@/types/agents';
import * as yaml from 'js-yaml';
import { marketApi } from '@/services/api/services/market';

export function useAgents(workspaceId?: string) {
  const modeList = ref<Agent[]>([]);
  const loadingAgents = ref(false);

  // Agent对话框相关
  const showModeDialog = ref(false);
  const showViewModeDialog = ref(false);
  const editingMode = ref<string | null>(null);
  const viewingMode = ref<Agent | null>(null);
  const modeForm = ref({
    slug: '',
    name: '',
    description: '',
    roleDefinition: '',
    whenToUse: '',
    customInstructions: '',
    groups: [] as string[]
  });
  const modeYamlContent = ref('');
  const savingMode = ref(false);

  // Mode Rules管理
  const showModeRulesDialog = ref(false);
  const editingModeRules = ref<Agent | null>(null);
  const modeRulesContent = ref('');
  const modeRulesDirectory = ref<string | null>(null);
  const modeRuleFiles = ref<Array<{ name: string; content: string }>>([]);
  const currentRuleFile = ref<{ name: string; content: string } | null>(null);
  const modeRuleFilesLoading = ref(false);

  // 市场对话框相关
  const showMarketDialog = ref(false);
  const installingFromMarket = ref(false);

  // 加载智能体列表
  const loadAgents = async (reload = false) => {
    if (!workspaceId) return;

    loadingAgents.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getModes(workspaceId, reload);
      modeList.value = response.modes || [];
    } catch (error: unknown) {
      ElMessage.error('加载智能体列表失败');
      console.error('Failed to load agents:', error);
    } finally {
      loadingAgents.value = false;
    }
  };

  // 显示创建智能体对话框
  const showCreateModeDialog = () => {
    editingMode.value = null;
    resetModeForm();
    showModeDialog.value = true;
  };

  // 编辑智能体
  const editMode = async (agent: Agent) => {
    if (agent.source === 'system') {
      ElMessage.warning('系统模式不可编辑');
      return;
    }

    editingMode.value = agent.slug;
    modeForm.value = {
      slug: agent.slug,
      name: agent.name,
      description: agent.description || '',
      roleDefinition: '',
      whenToUse: '',
      customInstructions: '',
      groups: []
    };

    // 将模式配置转换为 YAML 格式（使用下划线格式，更符合YAML惯例）
    const modeConfig = {
      slug: agent.slug,
      name: agent.name,
      description: agent.description,
      role_definition: agent.role_definition || '',
      when_to_use: agent.when_to_use || '',
      custom_instructions: agent.custom_instructions || '',
      groups: agent.groups || []
    };

    try {
      modeYamlContent.value = yaml.dump(modeConfig, {
        indent: 2,
        lineWidth: -1,
        noRefs: true,
        sortKeys: false
      });
    } catch (error) {
      console.error('Failed to convert mode to YAML:', error);
      modeYamlContent.value = '# Error converting mode to YAML\n' + JSON.stringify(modeConfig, null, 2);
    }

    showModeDialog.value = true;
  };

  // 验证YAML格式和必需字段
  const validateYamlConfig = (yamlContent: string): { valid: boolean; error?: string; config?: Record<string, unknown> } => {
    if (!yamlContent.trim()) {
      return { valid: false, error: 'YAML内容不能为空' };
    }

    try {
      const parsedConfig = yaml.load(yamlContent) as Record<string, unknown>;

      // 检查是否为对象
      if (typeof parsedConfig !== 'object' || parsedConfig === null) {
        return { valid: false, error: 'YAML必须是一个对象（字典）' };
      }

      // 验证必需字段
      const requiredFields = ['slug', 'name', 'description'];
      for (const field of requiredFields) {
        if (!parsedConfig[field]) {
          return { valid: false, error: `缺少必需字段: ${field}` };
        }
      }

      // 验证字段类型
      if (typeof parsedConfig.slug !== 'string' || !parsedConfig.slug.trim()) {
        return { valid: false, error: 'slug必须是非空字符串' };
      }
      if (typeof parsedConfig.name !== 'string' || !parsedConfig.name.trim()) {
        return { valid: false, error: 'name必须是非空字符串' };
      }
      if (typeof parsedConfig.description !== 'string' || !parsedConfig.description.trim()) {
        return { valid: false, error: 'description必须是非空字符串' };
      }

      // 验证groups是否为数组（如果存在）
      if (parsedConfig.groups !== undefined && !Array.isArray(parsedConfig.groups)) {
        return { valid: false, error: 'groups必须是数组' };
      }

      return { valid: true, config: parsedConfig };
    } catch (error) {
      return { valid: false, error: `YAML解析失败: ${(error as Error).message}` };
    }
  };

  // 保存智能体
  const saveMode = async () => {
    if (!workspaceId) {
      return;
    }

    savingMode.value = true;
    try {
      if (editingMode.value) {
        // 编辑模式：验证并解析YAML
        const validation = validateYamlConfig(modeYamlContent.value);
        if (!validation.valid) {
          ElMessage.error(validation.error);
          return;
        }

        const parsedConfig = validation.config!;

        // 转换字段名为API期望的驼峰格式
        const apiData = {
          slug: parsedConfig.slug as string,
          name: parsedConfig.name as string,
          description: parsedConfig.description as string,
          roleDefinition: (parsedConfig.role_definition || parsedConfig.roleDefinition || '') as string,
          whenToUse: (parsedConfig.when_to_use || parsedConfig.whenToUse || '') as string,
          customInstructions: (parsedConfig.custom_instructions || parsedConfig.customInstructions || '') as string,
          groups: (parsedConfig.groups as string[]) || []
        };

        await apiManager.getWorkspacesApi().updateMode(
          workspaceId,
          editingMode.value,
          apiData
        );
        ElMessage.success('智能体更新成功');
      } else {
        // 创建模式：使用表单数据
        if (!modeForm.value.slug || !modeForm.value.name || !modeForm.value.description) {
          ElMessage.warning('请填写必填字段');
          return;
        }

        // 获取当前mode列表
        const response = await apiManager.getWorkspacesApi().getModes(workspaceId);
        const currentModes = response.modes || [];

        // 添加新mode到列表（只添加自定义mode，不包括系统mode）
        const customModes = currentModes.filter((m: Agent) => m.source !== 'system');

        // 添加新的mode
        customModes.push({
          slug: modeForm.value.slug,
          name: modeForm.value.name,
          description: modeForm.value.description,
          role_definition: '',
          when_to_use: '',
          custom_instructions: '',
          groups: []
        });

        // 更新mode settings
        await apiManager.getWorkspacesApi().updateModeSettings(
          workspaceId,
          { customModes }
        );

        // 重新加载配置
        await apiManager.getWorkspacesApi().reloadWorkspaceConfig(
          workspaceId,
          'modes',
          true
        );

        ElMessage.success('智能体创建成功');
      }

      showModeDialog.value = false;
      await loadAgents(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '操作失败');
      console.error('Failed to save mode:', error);
    } finally {
      savingMode.value = false;
    }
  };

  // 删除智能体
  const deleteMode = async (slug: string) => {
    if (!workspaceId) return;

    try {
      await ElMessageBox.confirm(
        `确定要删除智能体 "${slug}" 吗？此操作不可撤销。`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      await apiManager.getWorkspacesApi().deleteModeConfig(workspaceId, slug);
      ElMessage.success('智能体删除成功');
      await loadAgents(true);
    } catch (error: unknown) {
      if (error !== 'cancel') {
        const err = error as { response?: { data?: { detail?: string } } };
        ElMessage.error(err.response?.data?.detail || '删除失败');
        console.error('Failed to delete mode:', error);
      }
    }
  };

  // 查看智能体详情
  const viewMode = async (agent: Agent) => {
    viewingMode.value = agent;
    showViewModeDialog.value = true;
  };

  // 编辑智能体规则
  const editModeRules = async (agent: Agent) => {
    editingModeRules.value = agent;
    modeRulesContent.value = '';
    modeRulesDirectory.value = null;
    modeRuleFiles.value = [];
    currentRuleFile.value = null;

    showModeRulesDialog.value = true;
    await loadModeRules(agent);
  };

  // 加载模式规则
  const loadModeRules = async (agent: Agent) => {
    if (!workspaceId) return;

    modeRuleFilesLoading.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getModeRules(
        workspaceId,
        agent.slug
      );

      // API返回的rules是一个Record<string, string>对象
      if (response.rules) {
        // 将rules对象转换为文件列表
        const ruleFiles = Object.entries(response.rules).map(([fileName, content]) => ({
          name: fileName,
          content: content,
          path: fileName,
          type: 'file' as const,
          level: 0,
          children: []
        }));

        modeRuleFiles.value = ruleFiles;

        // 如果有多个文件，默认显示第一个（通常是rules.md）
        if (ruleFiles.length > 0) {
          // 优先选择 rules.md
          const mainRule = ruleFiles.find(f => f.name === 'rules.md') || ruleFiles[0];
          currentRuleFile.value = mainRule;
          modeRulesContent.value = mainRule.content;
        }
      }

      if (response.directory) {
        modeRulesDirectory.value = response.directory;
      }
    } catch (error: unknown) {
      ElMessage.warning('加载规则失败，可能该智能体没有配置规则文件');
      console.error('Failed to load mode rules:', error);
      // 对话框已经打开，显示空状态
    } finally {
      modeRuleFilesLoading.value = false;
    }
  };

  // 保存模式规则
  const saveModeRules = async () => {
    if (!workspaceId || !editingModeRules.value) return;

    try {
      await apiManager.getWorkspacesApi().updateModeRules(
        workspaceId,
        editingModeRules.value.slug,
        { rules: modeRulesContent.value }
      );
      ElMessage.success('规则保存成功');
      showModeRulesDialog.value = false;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '保存失败');
      console.error('Failed to save mode rules:', error);
    }
  };

  // 选择规则文件
  const selectRuleFile = (file: { name: string; content: string }) => {
    currentRuleFile.value = file;
    modeRulesContent.value = file.content;
  };

  // 重置模式表单
  const resetModeForm = () => {
    modeForm.value = {
      slug: '',
      name: '',
      description: '',
      roleDefinition: '',
      whenToUse: '',
      customInstructions: '',
      groups: []
    };
    modeYamlContent.value = '';
  };

  // 打开市场对话框
  const openMarketDialog = (type: 'agent' | 'skill' | 'plugin') => {
    if (type === 'agent') {
      showMarketDialog.value = true;
    } else {
      ElMessage.info(`${type} 市场功能开发中...`);
    }
  };

  // 从市场安装智能体
  const installFromMarket = async (agentName: string, force = false) => {
    if (!workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    installingFromMarket.value = true;
    try {
      const response = await marketApi.installAgent(agentName, workspaceId, force);

      if (response.success) {
        ElMessage.success(`智能体 "${agentName}" 安装成功`);

        // 关键步骤：调用后端API重新加载配置
        try {
          const result = await apiManager.getWorkspacesApi().reloadWorkspaceConfig(
            workspaceId,
            'modes',  // 重新加载modes配置
            true  // 强制重新加载
          );
        } catch (error) {
          console.error('[Agents] Failed to reload config:', error);
          // 即使重新加载失败,也继续刷新前端列表
        }

        // 重新加载智能体列表
        await loadAgents(true);
        // 关闭市场对话框
        showMarketDialog.value = false;
      } else {
        ElMessage.error(`安装失败: ${response.message}`);
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '安装失败');
      console.error('Failed to install agent:', error);
    } finally {
      installingFromMarket.value = false;
    }
  };

  return {
    modeList,
    loadingAgents,
    loadAgents,
    showCreateModeDialog,
    editMode,
    saveMode,
    deleteMode,
    viewMode,
    editModeRules,
    saveModeRules,
    selectRuleFile,
    openMarketDialog,
    installFromMarket,
    // 对话框状态
    showModeDialog,
    showViewModeDialog,
    showModeRulesDialog,
    editingMode,
    viewingMode,
    editingModeRules,
    modeForm,
    modeYamlContent,
    savingMode,
    modeRulesContent,
    modeRulesDirectory,
    modeRuleFiles,
    currentRuleFile,
    modeRuleFilesLoading,
    // 市场相关状态
    showMarketDialog,
    installingFromMarket
  };
}
