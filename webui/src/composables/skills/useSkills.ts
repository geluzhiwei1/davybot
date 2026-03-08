import { ref, computed } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { Skill } from '@/types/skills';
import { skillsApi } from '@/services/api/services/skills';
import type { SkillFileTreeItem } from '@/services/api/services/skills';
import { marketApi } from '@/services/api/services/market';

export function useSkills(workspaceId?: string) {
  const skillsList = ref<Skill[]>([]);
  const loadingSkills = ref(false);
  const skillsFilter = ref({
    mode: '',
    scope: '',
    search: ''
  });

  // 技能编辑相关变量
  const editSkillDialogVisible = ref(false);
  const editSkillForm = ref({
    name: '',
    description: '',
    content: ''
  });
  const savingSkill = ref(false);
  const currentEditingSkill = ref<Skill | null>(null);

  // 新建技能相关变量
  const createSkillDialogVisible = ref(false);
  const createSkillForm = ref({
    name: '',
    description: '',
    content: '',
    scope: 'workspace'
  });
  const creatingSkill = ref(false);

  // 技能文件编辑器相关变量
  const showSkillEditorDialog = ref(false);
  const editingSkill = ref<Skill | null>(null);
  const skillFileTree = ref<SkillFileTreeItem[]>([]);
  const skillFileTreeLoading = ref(false);
  const currentSkillFile = ref<SkillFileTreeItem | null>(null);
  const savingSkillFile = ref(false);

  // 市场对话框相关
  const showMarketDialog = ref(false);
  const installingFromMarket = ref(false);

  // 过滤后的技能列表
  const filteredSkills = computed(() => {
    let filtered = [...skillsList.value];

    // 按模式过滤
    if (skillsFilter.value.mode) {
      filtered = filtered.filter(skill => skill.mode === skillsFilter.value.mode);
    }

    // 按范围过滤
    if (skillsFilter.value.scope) {
      filtered = filtered.filter(skill => skill.scope === skillsFilter.value.scope);
    }

    // 按搜索关键词过滤
    if (skillsFilter.value.search) {
      const searchLower = skillsFilter.value.search.toLowerCase();
      filtered = filtered.filter(skill =>
        skill.name.toLowerCase().includes(searchLower) ||
        skill.description.toLowerCase().includes(searchLower)
      );
    }

    return filtered;
  });

  // 加载技能列表
  const loadSkills = async (forceReload: boolean = false) => {
    if (!workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    loadingSkills.value = true;
    try {
      const response = await apiManager.getSkillsApi().listSkills({
        workspace_id: workspaceId,
        force_reload: forceReload
      });
      skillsList.value = response.skills || [];
      ElMessage.success(`已加载 ${skillsList.value.length} 个技能`);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg = err.response?.data?.detail || err.message || '加载技能列表失败';
      ElMessage.error(`加载技能列表失败: ${errorMsg}`);
      console.error('Failed to load skills:', error);
    } finally {
      loadingSkills.value = false;
    }
  };

  // 过滤技能
  const filterSkills = () => {
    // filteredSkills computed property 会自动更新
  };

  // 打开编辑技能对话框
  const openEditSkillDialog = async (skill: Skill) => {
    currentEditingSkill.value = skill;
    editSkillForm.value = {
      name: skill.name,
      description: skill.description,
      content: ''
    };

    // 先打开对话框
    editSkillDialogVisible.value = true;

    // 然后获取技能的完整内容
    try {
      const contentResponse = await skillsApi.getSkillContent(skill.name, {
        workspace_id: workspaceId
      });
      editSkillForm.value.content = contentResponse.content || '';
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg = err.response?.data?.detail || err.message || '未知错误';
      ElMessage.warning(`加载技能内容失败: ${errorMsg}，将显示基本信息`);
      console.error('Failed to load skill content:', error);
      // 对话框已经打开，用户可以看到基本信息
    }
  };

  // 保存技能
  const saveSkill = async () => {
    if (!currentEditingSkill.value || !workspaceId) {
      return;
    }

    savingSkill.value = true;
    try {
      await skillsApi.updateSkill(
        currentEditingSkill.value.name,
        {
          name: editSkillForm.value.name,
          description: editSkillForm.value.description,
          content: editSkillForm.value.content
        },
        { workspace_id: workspaceId }
      );
      ElMessage.success('技能保存成功');
      editSkillDialogVisible.value = false;
      // 重新加载技能列表
      await loadSkills();
    } catch (error) {
      ElMessage.error('技能保存失败');
      console.error('Failed to save skill:', error);
    } finally {
      savingSkill.value = false;
    }
  };

  // 删除技能
  const deleteSkill = async (skill: Skill) => {
    if (!workspaceId) {
      return;
    }

    try {
      await ElMessageBox.confirm(
        `确定要删除技能 "${skill.name}" 吗？此操作不可撤销。`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      const response = await skillsApi.deleteSkill(skill.name, {
        workspace_id: workspaceId
      });

      // 清空本地列表以确保重新加载
      skillsList.value = [];

      // 添加短暂延迟确保文件系统操作完成
      await new Promise(resolve => setTimeout(resolve, 300));

      // 重新加载技能列表
      await loadSkills();

      // 显示成功消息（如果有重复技能提示）
      if (response.message && response.message.includes('Note:')) {
        ElMessage.warning({
          message: response.message,
          duration: 5000
        });
      } else {
        ElMessage.success('技能删除成功');
      }
    } catch (error) {
      if (error !== 'cancel') {
        ElMessage.error('技能删除失败');
        console.error('Failed to delete skill:', error);
        // 失败时也重新加载列表以确保状态一致
        await loadSkills();
      }
    }
  };

  // 打开新建技能对话框
  const openCreateSkillDialog = () => {
    createSkillForm.value = {
      name: '',
      description: '',
      content: '',
      scope: 'workspace'
    };
    createSkillDialogVisible.value = true;
  };

  // 创建技能
  const createSkill = async () => {
    if (!createSkillForm.value.name || !workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    creatingSkill.value = true;
    try {
      await skillsApi.createSkill(
        {
          name: createSkillForm.value.name,
          description: createSkillForm.value.description,
          content: createSkillForm.value.content,
          scope: createSkillForm.value.scope
        },
        { workspace_id: workspaceId }
      );
      ElMessage.success('技能创建成功');
      createSkillDialogVisible.value = false;
      // 重新加载技能列表
      await loadSkills();
    } catch (error) {
      ElMessage.error('技能创建失败');
      console.error('Failed to create skill:', error);
    } finally {
      creatingSkill.value = false;
    }
  };

  // 打开技能文件编辑器
  const openSkillEditor = async (skill: Skill) => {
    editingSkill.value = skill;
    showSkillEditorDialog.value = true;

    // 加载技能文件树
    await loadSkillFileTree(skill.name);
  };

  // 加载技能文件树
  const loadSkillFileTree = async (skillName: string) => {
    if (!workspaceId) return;

    skillFileTreeLoading.value = true;
    try {
      const response = await skillsApi.getSkillFileTree(skillName, {
        workspace_id: workspaceId
      });
      skillFileTree.value = response.tree || [];
    } catch (error) {
      ElMessage.error('加载技能资源失败');
      console.error('Failed to load skill file tree:', error);
    } finally {
      skillFileTreeLoading.value = false;
    }
  };

  // 查看技能文件
  const viewSkillFile = async (fileItem: SkillFileTreeItem) => {
    if (!editingSkill.value || !workspaceId) return;

    currentSkillFile.value = fileItem;
    try {
      const response = await skillsApi.getSkillFileContent(
        editingSkill.value.name,
        fileItem.path,
        { workspace_id: workspaceId }
      );
      currentSkillFile.value = {
        ...fileItem,
        content: response.content
      };
    } catch (error) {
      ElMessage.error('加载文件内容失败');
      console.error('Failed to load file content:', error);
    }
  };

  // 打开市场对话框
  const openMarketDialog = (type: 'skill' | 'plugin' | 'agent') => {
    if (type === 'skill') {
      showMarketDialog.value = true;
    } else {
      ElMessage.info(`${type} 市场功能开发中...`);
    }
  };

  // 从市场安装技能
  const installFromMarket = async (skillName: string, force = false) => {
    if (!workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    installingFromMarket.value = true;
    try {
      const response = await marketApi.installSkill(skillName, workspaceId, force);

      if (response.success) {
        ElMessage.success(`技能 "${skillName}" 安装成功`);

        // 关键步骤：调用后端API重新加载配置
        try {
          const result = await apiManager.getWorkspacesApi().reloadWorkspaceConfig(
            workspaceId,
            'skills',  // 重新加载skills配置
            true  // 强制重新加载
          );
          if (result.success) {
            console.log('[Skills] Config reload result:', result);
          }
        } catch (error) {
          console.error('[Skills] Failed to reload config:', error);
          // 即使重新加载失败,也继续刷新前端列表
        }

        // 重新加载技能列表
        await loadSkills(true);
        // 关闭市场对话框
        showMarketDialog.value = false;
      } else {
        ElMessage.error(`安装失败: ${response.message}`);
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '安装失败');
      console.error('Failed to install skill:', error);
    } finally {
      installingFromMarket.value = false;
    }
  };

  // 获取技能统计
  const skillsStats = computed(() => ({
    total: skillsList.value.length,
    workspace: skillsList.value.filter(s => s.scope === 'workspace').length,
    user: skillsList.value.filter(s => s.scope === 'user').length,
    system: skillsList.value.filter(s => s.scope === 'system').length
  }));

  return {
    skillsList,
    loadingSkills,
    skillsFilter,
    filteredSkills,
    skillsStats,
    loadSkills,
    filterSkills,
    openEditSkillDialog,
    saveSkill,
    deleteSkill,
    openCreateSkillDialog,
    createSkill,
    openSkillEditor,
    openMarketDialog,
    installFromMarket,
    // 编辑相关状态
    editSkillDialogVisible,
    editSkillForm,
    savingSkill,
    currentEditingSkill,
    // 创建相关状态
    createSkillDialogVisible,
    createSkillForm,
    creatingSkill,
    // 文件编辑器相关状态
    showSkillEditorDialog,
    editingSkill,
    skillFileTree,
    skillFileTreeLoading,
    currentSkillFile,
    savingSkillFile,
    viewSkillFile,
    // 市场相关状态
    showMarketDialog,
    installingFromMarket
  };
}
