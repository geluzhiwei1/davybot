/* eslint-disable */
<template>
  <el-drawer v-model="visible" :title="t('workspaceSettings.title')" direction="rtl" :size="'80%'"
    class="workspace-settings-drawer" @close="handleClose">
    <template #header>
      <div class="drawer-header">
        <el-icon :size="20">
          <Setting />
        </el-icon>
        <span class="drawer-title">{{ t('workspaceSettings.title') }}</span>
      </div>
    </template>

    <div class="drawer-content">
      <!-- Show warning if no workspace ID -->
      <el-empty v-if="!props.workspaceId" description="未选择工作区" />

      <!-- 添加 v-if 确保数据加载完成后再渲染 tabs，避免首次打开不显示内容的问题 -->
      <el-tabs v-else-if="settingsLoaded" v-model="activeTab" type="border-card" tab-position="left">
        <!-- Workspace Tab (simplified, only basic info) -->
        <el-tab-pane :label="t('workspaceSettings.tabs.workspace')" name="workspace">
          <div class="workspace-config">
            <el-alert :title="t('workspaceSettings.workspace.description')" type="info" :closable="false" show-icon
              style="margin-bottom: 20px">
              <template #default>
                <p style="margin: 0; font-size: 13px;">
                  {{ t('workspaceSettings.workspace.description') }}
                </p>
              </template>
            </el-alert>

            <!-- Basic Info Form -->
            <el-scrollbar max-height="calc(100vh - 200px)">
              <el-form :model="workspaceInfo" label-width="140px" class="workspace-form">
                <el-form-item :label="t('workspaceSettings.workspace.workspaceId')">
                  <el-input v-model="workspaceInfo.id" disabled />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.workspace.currentPath')">
                  <el-input v-model="workspaceInfo.path" disabled />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.workspace.createdAt')">
                  <el-input v-model="workspaceInfo.createdAt" disabled />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.workspace.lastModified')">
                  <el-input v-model="workspaceInfo.lastModified" disabled />
                </el-form-item>
              </el-form>
            </el-scrollbar>
          </div>
        </el-tab-pane>
        <!-- LLM Provider 管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.llmProvider')" name="llm-providers">
          <div class="provider-management">
            <div class="provider-header">
              <el-alert title="Provider 管理" type="info" :closable="false" show-icon>
                <template #default>
                  <p style="margin: 0; font-size: 13px;">
                    管理用户和工作区的 LLM Provider 配置。所有配置保存在 <code>settings.json</code>
                  </p>
                </template>
              </el-alert>

              <div class="provider-actions" style="margin-top: 16px; display: flex; gap: 8px;">
                <el-button type="primary" @click="showCreateProviderDialog">
                  <el-icon>
                    <Plus />
                  </el-icon>
                  添加 Provider
                </el-button>
                <el-button @click="loadLLMSettings" :loading="loading">
                  <el-icon>
                    <Refresh />
                  </el-icon>
                  刷新
                </el-button>
              </div>
            </div>

            <!-- Provider 列表 -->
            <el-table :data="providerList" style="width: 100%; margin-top: 16px;" border v-loading="loading">
              <el-table-column prop="name" label="名称" width="200">
                <template #default="scope">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span>{{ scope.row.name }}</span>
                    <el-tag v-if="scope.row.name === llmSettings.currentApiConfigName" type="success"
                      size="small">默认</el-tag>
                  </div>
                </template>
              </el-table-column>

              <el-table-column prop="source" label="来源" width="100">
                <template #default="scope">
                  <el-tag :type="scope.row.source === 'user' ? 'warning' : 'success'" size="small">
                    {{ scope.row.source === 'user' ? '用户级' : '工作区级' }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column prop="apiProvider" label="类型" width="150">
                <template #default="scope">
                  <el-tag :type="getProviderTagType(scope.row.apiProvider)" size="small">
                    {{ getProviderDisplayName(scope.row.apiProvider) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column prop="modelId" label="模型 ID" width="200" show-overflow-tooltip />

              <el-table-column prop="baseUrl" label="Base URL" show-overflow-tooltip />

              <el-table-column label="高级设置" width="180">
                <template #default="scope">
                  <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                    <el-tag v-if="scope.row.config.config?.diffEnabled || scope.row.config.diffEnabled" size="small"
                      type="info">Diff</el-tag>
                    <el-tag v-if="scope.row.config.config?.todoListEnabled || scope.row.config.todoListEnabled"
                      size="small" type="info">TODO</el-tag>
                    <el-tag
                      v-if="scope.row.config.config?.enableReasoningEffort || scope.row.config.enableReasoningEffort"
                      size="small" type="warning">推理</el-tag>
                  </div>
                </template>
              </el-table-column>

              <el-table-column label="操作" width="200" align="center" fixed="right">
                <template #default="scope">
                  <el-button size="small" @click="viewProvider(scope.row)">查看</el-button>
                  <el-button size="small" type="primary" @click="editProvider(scope.row)">编辑</el-button>
                  <el-button size="small" type="danger" @click="deleteProvider(scope.row.name)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Skills Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.skills')" name="skills">
          <div class="skills-settings">
            <el-alert :title="t('workspaceSettings.skills.title')" type="info" :closable="false" show-icon
              style="margin-bottom: 16px;">
              <template #default>
                <p style="margin: 0; font-size: 13px;">`
                  {{ t('workspaceSettings.skills.description') }}
                  <br>• {{ t('workspaceSettings.skills.workspaceDir') }}<code>.dawei/skills/</code>
                  <br>• {{ t('workspaceSettings.skills.globalDir') }}<code>~/.dawei/skills/</code>
                </p>
              </template>
            </el-alert>

            <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">
                {{ t('workspaceSettings.skills.availableSkills') }} ({{ skillsList.length }})
              </span>
              <div>
                <el-button type="primary" size="small" @click="openCreateSkillDialog">
                  <el-icon>
                    <Plus />
                  </el-icon>
                  {{ t('workspaceSettings.skills.createSkill') }}
                </el-button>
                <el-button type="success" size="small" @click="openMarketDialog('skill')" style="margin-left: 8px;">
                  <el-icon>
                    <ShoppingCart />
                  </el-icon>
                  {{ t('workspaceSettings.skills.marketInstall') }}
                </el-button>
                <el-button type="primary" size="small" @click="loadSkills" :loading="loadingSkills"
                  style="margin-left: 8px;">
                  <el-icon>
                    <Refresh />
                  </el-icon>
                  {{ t('workspaceSettings.skills.refreshList') }}
                </el-button>
              </div>
            </div>

            <!-- 过滤器 -->
            <div style="margin-bottom: 16px; display: flex; gap: 12px;">
              <el-select v-model="skillsFilter.mode" :placeholder="t('workspaceSettings.skills.filter.mode')" clearable
                style="width: 150px;" @change="filterSkills">
                <el-option :label="t('workspaceSettings.skills.filter.allModes')" value="" />
                <el-option label="Code" value="code" />
                <el-option label="Ask" value="ask" />
                <el-option label="Architect" value="architect" />
                <el-option label="Debug" value="debug" />
              </el-select>

              <el-select v-model="skillsFilter.scope" :placeholder="t('workspaceSettings.skills.filter.scope')"
                clearable style="width: 150px;" @change="filterSkills">
                <el-option :label="t('workspaceSettings.skills.filter.allScopes')" value="" />
                <el-option label="项目" value="workspace" />
                <el-option label="系统" value="system" />
                <el-option label="全局" value="user" />
              </el-select>

              <el-input v-model="skillsFilter.search" :placeholder="t('workspaceSettings.skills.filter.search')"
                style="width: 250px;" clearable @input="filterSkills">
                <template #prefix>
                  <el-icon>
                    <Search />
                  </el-icon>
                </template>
              </el-input>
            </div>

            <!-- Skills 列表 -->
            <el-table :data="filteredSkills" stripe v-loading="loadingSkills" style="width: 100%;">
              <el-table-column prop="icon" :label="t('workspaceSettings.skills.table.icon')" width="60">
                <template #default="scope">
                  <span style="font-size: 20px;">{{ scope.row.icon }}</span>
                </template>
              </el-table-column>

              <el-table-column prop="name" :label="t('workspaceSettings.skills.table.name')" width="200"
                show-overflow-tooltip />

              <el-table-column prop="description" :label="t('workspaceSettings.skills.table.description')"
                show-overflow-tooltip />

              <el-table-column prop="category" :label="t('workspaceSettings.skills.table.category')" width="120">
                <template #default="scope">
                  <el-tag v-if="scope.row.category" size="small" type="info">
                    {{ scope.row.category }}
                  </el-tag>
                  <span v-else style="color: var(--el-text-color-secondary);">-</span>
                </template>
              </el-table-column>

              <el-table-column prop="mode" :label="t('workspaceSettings.skills.table.mode')" width="120">
                <template #default="scope">
                  <el-tag v-if="scope.row.mode" size="small" type="primary">
                    {{ scope.row.mode }}
                  </el-tag>
                  <span v-else style="color: var(--el-text-color-secondary);">-</span>
                </template>
              </el-table-column>

              <el-table-column prop="scope" :label="t('workspaceSettings.skills.table.scope')" width="100">
                <template #default="scope">
                  <el-tag :type="getScopeTagType(scope.row.scope)" size="small">
                    {{ getScopeDisplayName(scope.row.scope) }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column :label="t('workspaceSettings.skills.table.actions')" width="160" align="center">
                <template #default="scope">
                  <el-button v-if="scope.row.scope !== 'system'" type="primary" size="small" link
                    @click="openSkillEditorDialog(scope.row)">
                    <el-icon>
                      <Edit />
                    </el-icon>
                    {{ t('workspaceSettings.skills.actions.edit') }}
                  </el-button>
                  <el-popconfirm v-if="scope.row.scope !== 'system'"
                    :title="t('workspaceSettings.skills.deleteConfirm', { name: scope.row.name })"
                    @confirm="deleteSkill(scope.row)">
                    <template #reference>
                      <el-button type="danger" size="small" link>
                        <el-icon>
                          <Delete />
                        </el-icon>
                        {{ t('workspaceSettings.skills.actions.delete') }}
                      </el-button>
                    </template>
                  </el-popconfirm>
                  <span v-else style="color: var(--el-text-color-secondary); font-size: 12px;">-</span>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="!loadingSkills && filteredSkills.length === 0"
              :description="t('workspaceSettings.skills.noSkills')" />

            <!-- 技能编辑对话框 -->
            <el-dialog v-model="editSkillDialogVisible" :title="t('workspaceSettings.skills.editDialog.title')"
              width="700px">
              <el-form :model="editSkillForm" label-width="100px">
                <el-form-item :label="t('workspaceSettings.skills.editDialog.name')">
                  <el-input v-model="editSkillForm.name" />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.skills.editDialog.description')">
                  <el-input v-model="editSkillForm.description" type="textarea" :rows="2" />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.skills.editDialog.content')">
                  <el-input v-model="editSkillForm.content" type="textarea" :rows="15"
                    style="font-family: monospace;" />
                </el-form-item>
              </el-form>
              <template #footer>
                <el-button @click="editSkillDialogVisible = false">
                  {{ t('common.cancel') }}
                </el-button>
                <el-button type="primary" @click="saveSkill" :loading="savingSkill">
                  {{ t('common.save') }}
                </el-button>
              </template>
            </el-dialog>

            <!-- 新建技能对话框 -->
            <el-dialog v-model="createSkillDialogVisible" :title="t('workspaceSettings.skills.createDialog.title')"
              width="700px">
              <el-form :model="createSkillForm" label-width="100px">
                <el-form-item :label="t('workspaceSettings.skills.createDialog.name')" required>
                  <el-input v-model="createSkillForm.name"
                    :placeholder="t('workspaceSettings.skills.createDialog.namePlaceholder')" />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.skills.createDialog.description')">
                  <el-input v-model="createSkillForm.description" type="textarea" :rows="2" />
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.skills.createDialog.scope')">
                  <el-radio-group v-model="createSkillForm.scope">
                    <el-radio value="workspace">{{ t('workspaceSettings.skills.createDialog.workspace') }}</el-radio>
                    <el-radio value="user">{{ t('workspaceSettings.skills.createDialog.user') }}</el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-form-item :label="t('workspaceSettings.skills.createDialog.content')">
                  <el-input v-model="createSkillForm.content" type="textarea" :rows="15"
                    style="font-family: monospace;" />
                </el-form-item>
              </el-form>
              <template #footer>
                <el-button @click="createSkillDialogVisible = false">
                  {{ t('common.cancel') }}
                </el-button>
                <el-button type="primary" @click="createSkill" :loading="creatingSkill"
                  :disabled="!createSkillForm.name">
                  {{ t('workspaceSettings.skills.createDialog.create') }}
                </el-button>
              </template>
            </el-dialog>

            <!-- 技能文件编辑器对话框（带文件树） -->
            <el-dialog v-model="showSkillEditorDialog" :title="`编辑技能 - ${editingSkill?.name || ''}`" width="1100px"
              @close="closeSkillEditorDialog">
              <div v-if="editingSkill" style="display: flex; gap: 16px; height: 650px;">
                <!-- 左侧：文件树 -->
                <div style="width: 280px; display: flex; flex-direction: column; gap: 8px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600; font-size: 14px;">{{ t('workspaceSettings.skills.editor.files')
                    }}</span>
                    <el-button size="small" @click="refreshSkillFileTree" :icon="Refresh">
                      {{ t('workspaceSettings.skills.editor.refresh') }}
                    </el-button>
                  </div>

                  <div v-if="skillFileTreeLoading" style="display: flex; justify-content: center; padding: 20px;">
                    <el-icon class="is-loading" size="24">
                      <Loading />
                    </el-icon>
                  </div>
                  <div v-else-if="skillFileTree.length === 0"
                    style="padding: 20px; text-align: center; color: var(--el-text-color-secondary);">
                    {{ t('workspaceSettings.skills.editor.noFiles') }}
                  </div>
                  <div v-else
                    style="flex: 1; overflow-y: auto; border: 1px solid var(--el-border-color); border-radius: 4px; padding: 8px;">
                    <FileTreeNode v-for="item in skillFileTree" :key="item.path" :item="item"
                      :selected="currentSkillFile?.path === item.path" @item-click="handleSkillFileClick" />
                  </div>
                </div>

                <!-- 右侧：编辑器 -->
                <div style="flex: 1; display: flex; flex-direction: column;">
                  <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <el-tooltip v-if="currentSkillFile" :content="currentSkillFile.path" placement="top">
                      <span
                        style="font-weight: 600; font-size: 14px; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block;">
                        {{ currentSkillFile.name }}
                      </span>
                    </el-tooltip>
                    <span v-else style="font-weight: 600; font-size: 14px;">
                      {{ t('workspaceSettings.skills.editor.selectFile') }}
                    </span>
                    <el-tag v-if="currentSkillFile?.name === 'SKILL.md'" type="success" size="small">
                      {{ t('workspaceSettings.skills.editor.mainFile') }}
                    </el-tag>
                  </div>

                  <div v-if="currentSkillFile" ref="skillVditorRef" class="skill-editor-container" style="flex: 1;">
                  </div>
                  <div v-else
                    style="flex: 1; display: flex; align-items: center; justify-content: center; color: var(--el-text-color-secondary);">
                    {{ t('workspaceSettings.skills.editor.selectFileHint') }}
                  </div>
                </div>
              </div>

              <template #footer>
                <el-button @click="showSkillEditorDialog = false">{{ t('common.cancel') }}</el-button>
                <el-button type="primary" @click="saveSkillFile" :loading="savingSkillFile"
                  :disabled="!currentSkillFile">
                  {{ t('workspaceSettings.skills.editor.save') }}
                </el-button>
              </template>
            </el-dialog>
          </div>
        </el-tab-pane>

        <!-- Agents 管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.agents')" name="mode-settings">
          <div class="mode-settings">
            <el-alert :title="t('workspaceSettings.agents.title')" type="info" :closable="false" show-icon
              style="margin-bottom: 16px;">
              <template #default>
                <p style="margin: 0; font-size: 13px;">
                  {{ t('workspaceSettings.agents.description') }}
                </p>
              </template>
            </el-alert>

            <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">{{ t('workspaceSettings.agents.currentAgents') }}</span>
              <div>
                <el-button type="success" size="small" @click="openMarketDialog('agent')">
                  <el-icon>
                    <ShoppingCart />
                  </el-icon>
                  {{ t('workspaceSettings.agents.marketInstall') }}
                </el-button>
                <el-button type="primary" size="small" @click="showCreateModeDialog" style="margin-left: 8px;">
                  <el-icon>
                    <Plus />
                  </el-icon>
                  {{ t('workspaceSettings.agents.addAgent') }}
                </el-button>
              </div>
            </div>

            <el-table :data="modeList" stripe>
              <el-table-column prop="name" :label="t('workspaceSettings.agents.table.name')" width="200">
                <template #default="scope">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span>{{ scope.row.name }}</span>
                    <el-tag v-if="scope.row.is_default" type="success" size="small">{{
                      t('workspaceSettings.agents.table.default') }}</el-tag>
                  </div>
                </template>
              </el-table-column>

              <el-table-column prop="slug" :label="t('workspaceSettings.agents.table.slug')" width="180" />

              <el-table-column prop="source" :label="t('workspaceSettings.agents.table.source')" width="100">
                <template #default="scope">
                  <el-tag
                    :type="scope.row.source === 'system' ? 'info' : scope.row.source === 'user' ? 'warning' : 'success'"
                    size="small">
                    {{ scope.row.source === 'system' ? t('workspaceSettings.agents.sourceTypes.system') :
                      scope.row.source === 'user' ? t('workspaceSettings.agents.sourceTypes.user') :
                        t('workspaceSettings.agents.sourceTypes.workspace') }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column prop="description" :label="t('workspaceSettings.agents.table.description')"
                show-overflow-tooltip />

              <el-table-column :label="t('workspaceSettings.agents.table.actions')" width="280" fixed="right">
                <template #default="scope">
                  <el-button size="small" type="primary" @click="editMode(scope.row)"
                    :disabled="scope.row.source === 'system'">{{ t('workspaceSettings.agents.table.edit') }}</el-button>
                  <el-button size="small" type="warning" @click="editModeRules(scope.row)">
                    <el-icon>
                      <Document />
                    </el-icon>
                    Rules
                  </el-button>
                  <el-button size="small" type="danger" @click="deleteMode(scope.row.slug)"
                    :disabled="scope.row.source === 'system'">{{ t('workspaceSettings.agents.table.delete')
                    }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Plugins 管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.plugins')" name="plugins">
          <PluginConfigPanel :workspace-id="props.workspaceId" :can-edit="true"
            @open-market="openMarketDialog('plugin')" />
        </el-tab-pane>

        <!-- MCP Servers 管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.mcpServers')" name="mcp-servers">
          <div class="mcp-settings">
            <el-alert :title="t('workspaceSettings.mcpServers.title')" type="info" :closable="false" show-icon
              style="margin-bottom: 16px;">
              <template #default>
                <p style="margin: 0; font-size: 13px;">
                  {{ t('workspaceSettings.mcpServers.description') }}
                </p>
              </template>
            </el-alert>

            <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">{{ t('workspaceSettings.mcpServers.serverConfig') }}</span>
              <el-button type="primary" size="small" @click="showCreateMcpDialog">
                <el-icon>
                  <Plus />
                </el-icon>
                {{ t('workspaceSettings.mcpServers.addServer') }}
              </el-button>
            </div>

            <el-table :data="mcpServerList" stripe>
              <el-table-column prop="name" :label="t('workspaceSettings.mcpServers.table.name')" width="200" />
              <el-table-column prop="command" :label="t('workspaceSettings.mcpServers.table.command')"
                show-overflow-tooltip />
              <el-table-column prop="cwd" :label="t('workspaceSettings.mcpServers.table.cwd')" width="150" />
              <el-table-column prop="timeout" :label="t('workspaceSettings.mcpServers.table.timeout')" width="100" />
              <el-table-column :label="t('workspaceSettings.mcpServers.table.actions')" width="150" fixed="right">
                <template #default="scope">
                  <el-button size="small" @click="editMcpServer(scope.row)">{{
                    t('workspaceSettings.mcpServers.table.edit') }}</el-button>
                  <el-button size="small" type="danger" @click="deleteMcpServer(scope.row.name)">{{
                    t('workspaceSettings.mcpServers.table.delete') }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Features Tab (暂时禁用，功能未实现) -->
        <!--
        <el-tab-pane :label="t('workspaceSettings.tabs.features')" name="features">
          <el-scrollbar max-height="calc(100vh - 200px)">
            <el-form :model="workspaceConfig" label-width="180px" class="workspace-form">
              <!- - 技能系统配置 - ->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.skills') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.skillsEnabled')">
                <el-switch v-model="workspaceConfig.skills.enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.autoDiscovery')">
                <el-switch v-model="workspaceConfig.skills.auto_discovery" />
              </el-form-item>

              <!- - 工具系统配置 - ->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.tools') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.builtinToolsEnabled')">
                <el-switch v-model="workspaceConfig.tools.builtin_tools_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.systemToolsEnabled')">
                <el-switch v-model="workspaceConfig.tools.system_tools_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.userToolsEnabled')">
                <el-switch v-model="workspaceConfig.tools.user_tools_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.workspaceToolsEnabled')">
                <el-switch v-model="workspaceConfig.tools.workspace_tools_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.defaultTimeout')">
                <el-input-number v-model="workspaceConfig.tools.default_timeout" :min="10" :max="300"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxConcurrentExecutions')">
                <el-input-number v-model="workspaceConfig.tools.max_concurrent_executions" :min="1" :max="10"
                  style="width: 100%" />
              </el-form-item>

              <!- - 操作按钮 - ->
              <el-form-item style="margin-top: 30px;">
                <el-button type="primary" @click="saveWorkspaceConfig" :loading="saving">
                  {{ t('workspaceSettings.workspace.actions.save') }}
                </el-button>
                <el-button @click="loadWorkspaceConfig">
                  {{ t('workspaceSettings.workspace.actions.refresh') }}
                </el-button>
              </el-form-item>
            </el-form>
          </el-scrollbar>
        </el-tab-pane>
        -->

        <!-- Execution Config Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.execution')" name="execution">
          <el-scrollbar max-height="calc(100vh - 200px)">
            <el-form :model="workspaceConfig" label-width="180px" class="workspace-form">
              <!-- Agent 执行配置 -->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.agentExecution') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.agentMode')">
                <el-select v-model="workspaceConfig.agent.mode" style="width: 100%">
                  <el-option label="orchestrator" value="orchestrator" />
                  <el-option label="code" value="code" />
                  <el-option label="ask" value="ask" />
                  <el-option label="architect" value="architect" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.planModeConfirm')">
                <el-switch v-model="workspaceConfig.agent.plan_mode_confirm_required" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.enableAutoModeSwitch')">
                <el-switch v-model="workspaceConfig.agent.enable_auto_mode_switch" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.autoApproveTools')">
                <el-switch v-model="workspaceConfig.agent.auto_approve_tools" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxConcurrentSubtasks')">
                <el-input-number v-model="workspaceConfig.agent.max_concurrent_subtasks" :min="1" :max="10"
                  style="width: 100%" />
              </el-form-item>

              <!-- 检查点配置 -->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.checkpoint') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.checkpointInterval')">
                <el-input-number v-model="workspaceConfig.checkpoint.checkpoint_interval" :min="60" :max="3600"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxCheckpoints')">
                <el-input-number v-model="workspaceConfig.checkpoint.max_checkpoints" :min="1" :max="50"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.enableCompression')">
                <el-switch v-model="workspaceConfig.checkpoint.enable_compression" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.autoCreateEnabled')">
                <el-switch v-model="workspaceConfig.checkpoint.auto_create_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.minIntervalMinutes')">
                <el-input-number v-model="workspaceConfig.checkpoint.min_interval_minutes" :min="1" :max="60"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxCheckpointsPerTask')">
                <el-input-number v-model="workspaceConfig.checkpoint.max_checkpoints_per_task" :min="1" :max="100"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.validationEnabled')">
                <el-switch v-model="workspaceConfig.checkpoint.validation_enabled" />
              </el-form-item>

              <!-- 操作按钮 -->
              <el-form-item style="margin-top: 30px;">
                <el-button type="primary" @click="saveWorkspaceConfig" :loading="saving">
                  {{ t('workspaceSettings.workspace.actions.save') }}
                </el-button>
                <el-button @click="loadWorkspaceConfig">
                  {{ t('workspaceSettings.workspace.actions.refresh') }}
                </el-button>
              </el-form-item>
            </el-form>
          </el-scrollbar>
        </el-tab-pane>

        <!-- Compression & Memory Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.compression')" name="compression">
          <el-scrollbar max-height="calc(100vh - 200px)">
            <el-form :model="workspaceConfig" label-width="180px" class="workspace-form">
              <!-- 对话压缩配置 -->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.compression') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.compressionEnabled')">
                <el-switch v-model="workspaceConfig.compression.enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.preserveRecent')">
                <el-input-number v-model="workspaceConfig.compression.preserve_recent" :min="1" :max="100"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxTokens')">
                <el-input-number v-model="workspaceConfig.compression.max_tokens" :min="1000" :max="200000" :step="1000"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.compressionThreshold')">
                <el-slider v-model="workspaceConfig.compression.compression_threshold" :min="0" :max="1" :step="0.1"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.aggressiveThreshold')">
                <el-slider v-model="workspaceConfig.compression.aggressive_threshold" :min="0" :max="1" :step="0.1"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.pageSize')">
                <el-input-number v-model="workspaceConfig.compression.page_size" :min="5" :max="50"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxActivePages')">
                <el-input-number v-model="workspaceConfig.compression.max_active_pages" :min="1" :max="20"
                  style="width: 100%" />
              </el-form-item>

              <!-- 记忆集成 -->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.memoryIntegration') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.memoryIntegrationEnabled')">
                <el-switch v-model="workspaceConfig.compression.memory_integration_enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.autoExtractMemories')">
                <el-switch v-model="workspaceConfig.compression.auto_extract_memories" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.autoStoreMemories')">
                <el-switch v-model="workspaceConfig.compression.auto_store_memories" />
              </el-form-item>

              <!-- 记忆系统配置 -->
              <el-divider content-position="left">{{ t('workspaceSettings.workspace.memory') }}</el-divider>
              <el-form-item :label="t('workspaceSettings.workspace.memoryEnabled')">
                <el-switch v-model="workspaceConfig.memory.enabled" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.virtualPageSize')">
                <el-input-number v-model="workspaceConfig.memory.virtual_page_size" :min="500" :max="5000"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.maxActivePages')">
                <el-input-number v-model="workspaceConfig.memory.max_active_pages" :min="1" :max="20"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.defaultEnergy')">
                <el-slider v-model="workspaceConfig.memory.default_energy" :min="0" :max="1" :step="0.1"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.energyDecayRate')">
                <el-slider v-model="workspaceConfig.memory.energy_decay_rate" :min="0" :max="1" :step="0.05"
                  style="width: 100%" />
              </el-form-item>
              <el-form-item :label="t('workspaceSettings.workspace.minEnergyThreshold')">
                <el-slider v-model="workspaceConfig.memory.min_energy_threshold" :min="0" :max="1" :step="0.1"
                  style="width: 100%" />
              </el-form-item>

              <!-- 操作按钮 -->
              <el-form-item style="margin-top: 30px;">
                <el-button type="primary" @click="saveWorkspaceConfig" :loading="saving">
                  {{ t('workspaceSettings.workspace.actions.save') }}
                </el-button>
                <el-button @click="loadWorkspaceConfig">
                  {{ t('workspaceSettings.workspace.actions.refresh') }}
                </el-button>
              </el-form-item>
            </el-form>
          </el-scrollbar>
        </el-tab-pane>

        <!-- 执行环境 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.executionEnvironment')" name="environments">
          <el-tabs v-model="activeEnvironmentSubTab" type="card" class="environment-sub-tabs">
            <!-- 用户环境子 Tab -->
            <el-tab-pane :label="t('workspaceSettings.executionEnvironment.userEnvironment')" name="user">
              <el-form :model="uiEnvironments" label-width="120px" class="settings-form">
                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.browserName')">
                      <el-input v-model="uiEnvironments.browser_name" placeholder="Chrome" disabled />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.browserVersion')">
                      <el-input v-model="uiEnvironments.browser_version" placeholder="120.0.0.0" disabled />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.userOS')">
                      <el-input v-model="uiEnvironments.user_os" placeholder="Windows 11" disabled />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.userLanguage')">
                      <el-input v-model="uiEnvironments.user_language" placeholder="zh-CN" disabled />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.timezone')">
                      <el-input v-model="uiEnvironments.timezone" placeholder="Asia/Shanghai" disabled />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.user.screenResolution')">
                      <el-input v-model="uiEnvironments.screen_resolution" placeholder="1920x1080" disabled />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-form-item>
                  <el-button @click="loadUIEnvironments">{{ t('workspaceSettings.executionEnvironment.refresh')
                    }}</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 系统环境子 Tab -->
            <el-tab-pane :label="t('workspaceSettings.executionEnvironment.systemEnvironment')" name="system">
              <el-form :model="systemEnvironments" label-width="140px" class="settings-form">
                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.osName')">
                      <el-input v-model="systemEnvironments.os_name" placeholder="Linux" disabled />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.osVersion')">
                      <el-input v-model="systemEnvironments.os_version" placeholder="6.8.0-94-generic" disabled />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.pythonVersion')">
                      <el-input v-model="systemEnvironments.python_version" placeholder="3.12.0" disabled />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.cpuCount')">
                      <el-input-number v-model="systemEnvironments.cpu_count" :min="0" disabled style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.memoryTotal')">
                      <el-input-number v-model="systemEnvironments.memory_total" :min="0" disabled
                        style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.memoryAvailable')">
                      <el-input-number v-model="systemEnvironments.memory_available" :min="0" disabled
                        style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.diskTotal')">
                      <el-input-number v-model="systemEnvironments.disk_total" :min="0" disabled style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="t('workspaceSettings.executionEnvironment.system.diskAvailable')">
                      <el-input-number v-model="systemEnvironments.disk_available" :min="0" disabled
                        style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-form-item>
                  <el-button @click="loadSystemEnvironments">{{ t('workspaceSettings.executionEnvironment.refresh')
                    }}</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>
        <!-- 隐私配置 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.privacy')" name="privacy">
          <el-scrollbar max-height="calc(100vh - 200px)">
            <!-- 使用 PrivacyConfigSimplified 简化版组件 -->
            <PrivacyConfigSimplified :workspace-id="workspaceId" :initial-config="workspaceConfig.analytics"
              @config-changed="handlePrivacyConfigChanged" />
          </el-scrollbar>
        </el-tab-pane>

        <!-- 代理设置 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.proxy')" name="proxy">
          <el-scrollbar max-height="calc(100vh - 200px)">
            <el-form :model="proxyConfig" label-width="140px" class="settings-form" style="padding: 20px;">
              <el-alert
                :title="t('workspaceSettings.proxy.title')"
                type="info"
                :closable="false"
                style="margin-bottom: 20px;">
                <template #default>
                  <p>{{ t('workspaceSettings.proxy.description') }}</p>
                  <p style="margin-top: 8px;">
                    {{ t('workspaceSettings.proxy.supported') }}:
                    <code>http://127.0.0.1:7890</code> or <code>socks5://127.0.0.1:1080</code>
                  </p>
                </template>
              </el-alert>

              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item :label="t('workspaceSettings.proxy.httpProxy')">
                    <el-input v-model="proxyConfig.http_proxy" :placeholder="t('workspaceSettings.proxy.httpProxyPlaceholder')" clearable />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item :label="t('workspaceSettings.proxy.httpsProxy')">
                    <el-input v-model="proxyConfig.https_proxy" :placeholder="t('workspaceSettings.proxy.httpsProxyPlaceholder')" clearable />
                  </el-form-item>
                </el-col>
              </el-row>

              <el-form-item :label="t('workspaceSettings.proxy.noProxy')">
                <el-input v-model="proxyConfig.no_proxy" :placeholder="t('workspaceSettings.proxy.noProxyPlaceholder')">
                  <template #prepend>NO_PROXY</template>
                </el-input>
                <div class="form-tip">{{ t('workspaceSettings.proxy.noProxyTip') }}</div>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" @click="saveProxyConfig" :loading="savingProxy">
                  {{ t('workspaceSettings.proxy.save') }}
                </el-button>
                <el-button @click="loadProxyConfig">
                  {{ t('workspaceSettings.proxy.refresh') }}
                </el-button>
              </el-form-item>
            </el-form>
          </el-scrollbar>
        </el-tab-pane>

        <!-- 定时任务管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.scheduledTasks')" name="scheduled-tasks">
          <ScheduledTasksPanel v-if="props.workspaceId" :workspace-id="props.workspaceId" />
        </el-tab-pane>

        <!-- 检查点管理 Tab -->
        <el-tab-pane :label="t('workspaceSettings.tabs.checkpoints')" name="checkpoints">
          <CheckpointPanel v-if="props.workspaceId" :workspace-id="props.workspaceId" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Plugin Configuration Dialog -->
    <el-dialog v-model="pluginConfigDialogVisible" :title="`配置插件: ${selectedPlugin?.name || ''}`" width="700px"
      :close-on-click-modal="false">
      <PluginConfigForm v-if="pluginConfigDialogVisible && selectedPlugin" :workspace-id="props.workspaceId"
        :plugin-id="selectedPlugin.id" @saved="handlePluginConfigSaved" @cancel="pluginConfigDialogVisible = false" />
    </el-dialog>

    <!-- Provider 编辑/创建对话框 -->
    <el-dialog v-model="showProviderDialog" :title="editingProvider ? '编辑 Provider' : '添加 Provider'" width="800px">
      <el-form :model="providerForm" label-width="160px">
        <el-form-item label="Provider 名称" required>
          <el-input v-model="providerForm.name" placeholder="例如: my-openai" :disabled="editingProvider !== null" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            Provider 的唯一标识符,创建后不可修改
          </div>
        </el-form-item>

        <el-form-item label="保存位置" required v-if="editingProvider === null">
          <el-radio-group v-model="providerForm.saveLocation">
            <el-radio value="user">用户级（默认）</el-radio>
            <el-radio value="workspace">工作区级</el-radio>
          </el-radio-group>
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            用户级配置对所有工作区可用，工作区级配置仅对当前工作区有效
          </div>
        </el-form-item>

        <el-form-item label="API 类型" required>
          <el-select v-model="providerForm.apiProvider" placeholder="选择 API 类型" style="width: 100%"
            @change="onApiProviderChange" filterable>
            <el-option-group label="主流提供商">
              <el-option label="DeepSeek" value="deepseek" />
              <el-option label="Moonshot (Kimi)" value="moonshot" />
              <el-option label="Qwen (通义千问)" value="qwen" />
              <el-option label="GLM (智谱)" value="glm" />
              <el-option label="MiniMax" value="minimax" />
            </el-option-group>
            <el-option-group label="国际提供商">
              <el-option label="Gemini (Google)" value="gemini" />
              <el-option label="Claude (Anthropic)" value="claude" />
              <el-option label="OpenRouter" value="openrouter" />
            </el-option-group>
            <el-option-group label="其他">
              <el-option label="OpenAI兼容" value="openai" />
              <el-option label="Ollama (本地)" value="ollama" />
            </el-option-group>
          </el-select>
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            所有提供商都支持 Function Call (工具调用)
          </div>
        </el-form-item>

        <el-divider content-position="left">{{ getProviderDividerTitle(providerForm.apiProvider) }}</el-divider>

        <!-- OpenAI 兼容配置 (openai, deepseek, moonshot, qwen, glm, gemini, claude, minimax, openrouter) -->
        <template v-if="!isOllamaProvider(providerForm.apiProvider)">
          <el-form-item label="Base URL" required>
            <el-input v-model="providerForm.openAiBaseUrl" placeholder="https://api.openai.com/v1" />
          </el-form-item>

          <el-form-item label="API Key" required>
            <el-input v-model="providerForm.openAiApiKey" type="password" placeholder="sk-..." show-password />
          </el-form-item>

          <el-form-item label="模型 ID" required>
            <el-input v-model="providerForm.openAiModelId"
              placeholder="gpt-4o, deepseek-chat, claude-3-5-sonnet-20241022" />
          </el-form-item>

          <el-form-item label="自定义 Headers">
            <el-input v-model="customHeadersText" type="textarea" :rows="3"
              placeholder='例如: {&quot;anthropic-version&quot;: &quot;2023-06-01&quot;}' />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              JSON 格式，用于需要特殊请求头的提供商（如 Claude）
            </div>
          </el-form-item>

          <el-form-item label="旧版格式">
            <el-switch v-model="providerForm.openAiLegacyFormat" />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              某些 API 提供商需要使用旧版 OpenAI 格式
            </div>
          </el-form-item>
        </template>

        <!-- Ollama 配置 -->
        <template v-if="providerForm.apiProvider === 'ollama'">
          <el-form-item label="Base URL" required>
            <el-input v-model="providerForm.ollamaBaseUrl" placeholder="http://localhost:11434" />
          </el-form-item>

          <el-form-item label="模型 ID" required>
            <el-input v-model="providerForm.ollamaModelId" placeholder="llama3.1:latest, qwen2:7b" />
          </el-form-item>

          <el-form-item label="API Key">
            <el-input v-model="providerForm.ollamaApiKey" placeholder="key (可选)" />
          </el-form-item>
        </template>

        <el-divider content-position="left">高级设置</el-divider>

        <el-row :gutter="20" v-if="false">
          <el-col :span="12">
            <el-form-item label="启用差异编辑">
              <el-switch v-model="providerForm.diffEnabled" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用 TODO 列表">
              <el-switch v-model="providerForm.todoListEnabled" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="模糊匹配阈值">
              <el-input-number v-model="providerForm.fuzzyMatchThreshold" :min="0" :max="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="速率限制(秒)">
              <el-input-number v-model="providerForm.rateLimitSeconds" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="连续错误限制">
              <el-input-number v-model="providerForm.consecutiveMistakeLimit" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用推理强度">
              <el-switch v-model="providerForm.enableReasoningEffort" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <template #footer>
        <div style="display: flex; justify-content: flex-end; width: 100%; gap: 8px;">
          <el-button @click="testProvider" :loading="testingProvider"
            :disabled="!providerForm.openAiModelId && providerForm.apiProvider !== 'ollama'">
            测试 Tool Call
          </el-button>
          <span v-if="providerTestResult" style="display: flex; align-items: center;">
            <el-tag :type="providerTestResult.supported ? 'success' : 'danger'" size="small">
              {{ providerTestResult.supported ? '支持' : '不支持' }}
            </el-tag>
          </span>
          <el-button @click="showProviderDialog = false">取消</el-button>
          <el-button type="primary" @click="saveProvider" :loading="saving">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Provider 查看对话框 -->
    <el-dialog v-model="showViewProviderDialog" title="Provider 详情" width="700px">
      <el-descriptions :column="2" border v-if="viewingProvider">
        <el-descriptions-item label="Provider 名称">
          {{ viewingProvider.name }}
        </el-descriptions-item>
        <el-descriptions-item label="API 类型">
          <el-tag :type="getProviderTagType(viewingProvider.apiProvider)">
            {{ getProviderDisplayName(viewingProvider.apiProvider) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型 ID">
          {{ viewingProvider.modelId }}
        </el-descriptions-item>
        <el-descriptions-item label="Base URL">
          {{ viewingProvider.baseUrl }}
        </el-descriptions-item>

        <el-descriptions-item label="启用差异编辑" :span="2">
          <el-tag :type="viewingProvider.config.diffEnabled ? 'success' : 'info'" size="small">
            {{ viewingProvider.config.diffEnabled ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="启用 TODO 列表" :span="2">
          <el-tag :type="viewingProvider.config.todoListEnabled ? 'success' : 'info'" size="small">
            {{ viewingProvider.config.todoListEnabled ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="模糊匹配阈值">
          {{ viewingProvider.config.fuzzyMatchThreshold }}
        </el-descriptions-item>
        <el-descriptions-item label="速率限制(秒)">
          {{ viewingProvider.config.rateLimitSeconds }}
        </el-descriptions-item>

        <el-descriptions-item label="连续错误限制">
          {{ viewingProvider.config.consecutiveMistakeLimit }}
        </el-descriptions-item>
        <el-descriptions-item label="启用推理强度">
          <el-tag :type="viewingProvider.config.enableReasoningEffort ? 'success' : 'info'" size="small">
            {{ viewingProvider.config.enableReasoningEffort ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button type="primary" @click="showViewProviderDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Mode 编辑/创建对话框 -->
    <el-dialog v-model="showModeDialog" :title="editingMode ? '编辑模式配置' : '添加模式'" width="1000px" @close="resetModeForm">
      <el-alert title="YAML 格式配置" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            请使用 YAML 格式编辑模式配置。编辑模式下会加载现有配置。
          </p>
        </template>
      </el-alert>

      <el-form :model="modeForm" label-width="100px" v-if="!editingMode">
        <!-- 创建模式时只显示基本字段 -->
        <el-form-item label="模式标识符" required>
          <el-input v-model="modeForm.slug" placeholder="例如: my-custom-mode" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            模式的唯一标识符
          </div>
        </el-form-item>

        <el-form-item label="模式名称" required>
          <el-input v-model="modeForm.name" placeholder="例如: 🎨 自定义模式" />
        </el-form-item>

        <el-form-item label="模式描述" required>
          <el-input v-model="modeForm.description" type="textarea" :rows="2" placeholder="简要描述这个模式的用途" />
        </el-form-item>
      </el-form>

      <!-- YAML 编辑器 -->
      <div v-if="editingMode" style="margin-bottom: 16px;">
        <div style="margin-bottom: 8px; font-weight: 500;">模式配置 (YAML)</div>
        <CodeEditor v-model="modeYamlContent" language="yaml" height="500px" :line-numbers="true" />
      </div>

      <template #footer>
        <el-button @click="showModeDialog = false">取消</el-button>
        <el-button type="primary" @click="saveMode" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Mode 查看对话框 -->
    <el-dialog v-model="showViewModeDialog" title="模式详情" width="700px">
      <el-descriptions :column="1" border v-if="viewingMode">
        <el-descriptions-item label="模式名称">{{ viewingMode.name }}</el-descriptions-item>
        <el-descriptions-item label="标识符">{{ viewingMode.slug }}</el-descriptions-item>
        <el-descriptions-item label="描述">{{ viewingMode.description }}</el-descriptions-item>
        <el-descriptions-item label="角色定义">
          <div style="white-space: pre-wrap;">{{ viewingMode.roleDefinition }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="使用场景">
          <div style="white-space: pre-wrap;">{{ viewingMode.whenToUse }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="自定义指令" v-if="viewingMode.customInstructions">
          <div style="white-space: pre-wrap;">{{ viewingMode.customInstructions }}</div>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button type="primary" @click="showViewModeDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Mode Rules 编辑对话框 -->
    <el-dialog v-model="showModeRulesDialog" :title="`编辑 Rules - ${editingModeRules?.name || ''}`" width="1000px"
      @close="resetModeRulesForm">
      <div v-if="editingModeRules">
        <el-alert title="Rules 文件" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
          <template #default>
            <p style="margin: 0; font-size: 13px; margin-bottom: 8px;">
              Rules 目录: <code>{{ modeRulesDirectory || '未创建' }}</code>
            </p>
            <p style="margin: 0; font-size: 12px; color: var(--el-text-color-secondary);">
              该模式可以有多个规则文件，所有文件都会被应用到 AI Agent
            </p>
          </template>
        </el-alert>

        <!-- 文件列表和编辑器布局 -->
        <div style="display: flex; gap: 16px; height: 600px;">
          <!-- 左侧：文件列表 -->
          <div style="width: 250px; display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600; font-size: 14px;">规则文件</span>
              <el-button type="primary" size="small" @click="addNewRuleFile" :icon="Plus">
                新建
              </el-button>
            </div>

            <div style="flex: 1; overflow-y: auto; border: 1px solid var(--el-border-color); border-radius: 4px;">
              <div v-for="file in modeRuleFiles" :key="file.name" @click="selectRuleFile(file)"
                :class="['rule-file-item', { active: currentRuleFile?.name === file.name }]">
                <el-tooltip :content="file.name" placement="right">
                  <div
                    style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; cursor: pointer;">
                    <span style="font-size: 13px;">{{ file.name }}</span>
                    <el-button v-if="file.name !== 'mode.md'" type="danger" size="small" link
                      @click.stop="deleteRuleFile(file)" :icon="Delete">
                      删除
                    </el-button>
                  </div>
                </el-tooltip>
              </div>

              <el-empty v-if="modeRuleFiles.length === 0" description="暂无规则文件" :image-size="60" />
            </div>
          </div>

          <!-- 右侧：编辑器 -->
          <div style="flex: 1; display: flex; flex-direction: column;">
            <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
              <el-tooltip v-if="currentRuleFile" :content="currentRuleFile.name" placement="top">
                <span
                  style="font-weight: 600; font-size: 14px; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block;">
                  {{ currentRuleFile.name }}
                </span>
              </el-tooltip>
              <span v-else style="font-weight: 600; font-size: 14px;">
                请选择文件
              </span>
              <el-tag v-if="currentRuleFile?.name === 'mode.md'" type="info" size="small">
                主规则文件
              </el-tag>
            </div>

            <div v-if="currentRuleFile" ref="rulesVditorRef" class="rules-editor-container" style="flex: 1;"></div>
            <div v-else
              style="flex: 1; display: flex; align-items: center; justify-content: center; color: var(--el-text-color-secondary);">
              请选择或创建一个规则文件
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showModeRulesDialog = false">取消</el-button>
        <el-button type="primary" @click="saveModeRules" :loading="saving"
          :disabled="!currentRuleFile">保存当前文件</el-button>
      </template>
    </el-dialog>

    <!-- MCP 服务器编辑/创建对话框 -->
    <el-dialog v-model="showMcpDialog" :title="editingMcpServer ? '编辑 MCP 服务器' : '添加 MCP 服务器'" width="700px"
      @close="resetMcpForm">
      <el-form :model="mcpForm" label-width="140px">
        <el-form-item label="服务器名称" required>
          <el-input v-model="mcpForm.name" placeholder="例如: my-mcp-server" :disabled="editingMcpServer !== null" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            服务器的唯一标识符,创建后不可修改
          </div>
        </el-form-item>

        <el-form-item label="启动命令" required>
          <el-input v-model="mcpForm.command" placeholder="例如: fastmcp" />
        </el-form-item>

        <el-form-item label="命令参数">
          <el-input v-model="mcpForm.argsText" placeholder="例如: run main.py (用空格分隔多个参数)" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            多个参数用空格分隔
          </div>
        </el-form-item>

        <el-form-item label="工作目录">
          <el-input v-model="mcpForm.cwd" placeholder="例如: . (留空使用当前目录)" />
        </el-form-item>

        <el-form-item label="超时时间(秒)">
          <el-input-number v-model="mcpForm.timeout" :min="1" :max="600" placeholder="默认: 300" style="width: 100%;" />
        </el-form-item>

        <el-form-item label="始终允许的工具">
          <el-input v-model="mcpForm.alwaysAllowText" type="textarea" :rows="2"
            placeholder="例如: tool1, tool2 (用逗号或空格分隔)" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showMcpDialog = false">取消</el-button>
        <el-button type="primary" @click="saveMcpServer" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Market Dialog -->
    <MarketDialog v-model="marketDialogVisible" :workspace-id="workspaceId || ''" :initial-type="marketResourceType"
      @closed="() => loadSettings(true)" @installed="handleResourceInstalled" />
  </el-drawer>
</template>

/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<script setup lang="ts">
import { ref, watch, computed, nextTick, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import * as yaml from 'js-yaml';
import { Setting, Plus, Document, Refresh, Search, ShoppingCart, Edit, Delete, Loading } from '@element-plus/icons-vue';
import { apiManager } from '@/services/api';
import type { Skill } from '@/services/api';
import { skillsApi } from '@/services/api/services/skills';
import type { SkillFileTreeItem } from '@/services/api/services/skills';
import MarketDialog from '@/components/market/MarketDialog.vue';
import PluginConfigPanel from '@/components/workspace/PluginConfigPanel.vue';
import CodeEditor from '@/components/editor/CodeEditor.vue';
import FileTreeNode from './FileTreeNode.vue';
import ScheduledTasksPanel from './ScheduledTasksPanel.vue';
import CheckpointPanel from './CheckpointPanel.vue';
import type { ResourceType } from '@/services/api/services/market';
import Vditor from 'vditor';
import 'vditor/dist/index.css';
import { useThemeStore } from '@/stores/theme';

const { t } = useI18n();
const themeStore = useThemeStore();

const props = defineProps<{
  modelValue: boolean;
  workspaceId: string | null;
  initialTab?: string; // 初始显示的 tab
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const visible = ref(props.modelValue);
const activeTab = ref(props.initialTab || 'workspace');
const activeEnvironmentSubTab = ref('user');
const saving = ref(false);
const settingsLoaded = ref(false); // 用于控制 tabs 渲染时机，避免首次打开不显示内容
const testingProvider = ref(false);
const providerTestResult = ref<{ success: boolean; supported: boolean; message: string } | null>(null);

// Vditor refs for Rules editor
const rulesVditorRef = ref<HTMLDivElement | null>(null);
const rulesVditor = ref<Vditor | null>(null);
const rulesVditorInitialized = ref(false);

// 插件配置相关状态
const pluginConfigDialogVisible = ref(false);

// Market dialog state
const marketDialogVisible = ref(false);
const marketResourceType = ref<ResourceType>('skill');

// Plugin configuration dialog state
const selectedPlugin = ref<unknown>(null);

const uiEnvironments = ref({
  browser_name: '',
  browser_version: '',
  user_os: '',
  user_language: '',
  timezone: '',
  screen_resolution: ''
});

const systemEnvironments = ref({
  os_name: '',
  os_version: '',
  python_version: '',
  cpu_count: 0,
  memory_total: 0,
  memory_available: 0,
  disk_total: 0,
  disk_available: 0
});

// 工作区基本信息
const workspaceInfo = ref({
  id: '',
  path: '',
  createdAt: '',
  lastModified: ''
});

// 工作区配置
const workspaceConfig = ref({
  agent: {
    mode: 'orchestrator',
    plan_mode_confirm_required: true,
    enable_auto_mode_switch: false,
    auto_approve_tools: true,
    max_concurrent_subtasks: 3
  },
  checkpoint: {
    checkpoint_interval: 300,
    max_checkpoints: 10,
    enable_compression: true,
    auto_create_enabled: true,
    min_interval_minutes: 5,
    max_checkpoints_per_task: 50,
    validation_enabled: true
  },
  compression: {
    enabled: false,
    preserve_recent: 20,
    max_tokens: 100000,
    compression_threshold: 0.5,
    aggressive_threshold: 0.9,
    page_size: 20,
    max_active_pages: 5,
    memory_integration_enabled: true,
    auto_extract_memories: true,
    auto_store_memories: true
  },
  memory: {
    enabled: false,
    virtual_page_size: 2000,
    max_active_pages: 5,
    default_energy: 1.0,
    energy_decay_rate: 0.1,
    min_energy_threshold: 0.2
  },
  skills: {
    enabled: true,
    auto_discovery: true
  },
  tools: {
    builtin_tools_enabled: true,
    system_tools_enabled: true,
    user_tools_enabled: true,
    workspace_tools_enabled: true,
    default_timeout: 60,
    max_concurrent_executions: 3
  },
  logging: {
    level: 'INFO',
    dir: '~/.dawei/logs',
    max_file_size: 10,
    backup_count: 5,
    console_output: true,
    file_output: true,
    enable_performance_logging: true,
    sanitize_sensitive_data: true
  },
  analytics: {
    enabled: true,
    retention_days: 90,
    sampling_rate: 1.0,
    anonymize_enabled: true
  }
});

const llmSettings = ref({
  currentApiConfigName: null as string | null,
  allConfigs: {} as Record<string, unknown>,
  modeApiConfigs: {
    architect: '',
    code: '',
    ask: '',
    debug: '',
    orchestrator: ''
  },
  // 多级别配置
  userConfigs: [] as Array<{
    name: string;
    source: string;
    is_default: boolean;
    config: unknown;
  }>,
  workspaceConfigs: [] as Array<{
    name: string;
    source: string;
    is_default: boolean;
    config: unknown;
  }>
});

// Provider 管理相关
const showProviderDialog = ref(false);
const showViewProviderDialog = ref(false);
const editingProvider = ref<string | null>(null);
const viewingProvider = ref<unknown>(null);
const loading = ref(false);
const customHeadersText = ref('');
const providerForm = ref({
  name: '',
  apiProvider: 'openai',
  openAiBaseUrl: '',
  openAiApiKey: '',
  openAiModelId: '',
  openAiLegacyFormat: false,
  openAiHeaders: {} as Record<string, string>,
  ollamaBaseUrl: '',
  ollamaModelId: '',
  ollamaApiKey: '',
  diffEnabled: true,
  todoListEnabled: true,
  fuzzyMatchThreshold: 1,
  rateLimitSeconds: 0,
  consecutiveMistakeLimit: 3,
  enableReasoningEffort: true,
  saveLocation: 'user' as 'user' | 'workspace'  // 新增：保存位置
});

// Provider 列表 - 合并用户级和工作区级配置
const providerList = computed(() => {
  const providers: Array<{
    name: string;
    source: string;
    is_default: boolean;
    apiProvider: string;
    modelId: string;
    baseUrl: string;
    config: unknown;
  }> = [];

  // 添加用户级配置
  for (const item of llmSettings.value.userConfigs) {
    const config = item.config.config || item.config;
    providers.push({
      name: item.name,
      source: item.source,
      is_default: item.is_default,
      apiProvider: config.apiProvider || 'openai',
      modelId: config.openAiModelId || config.ollamaModelId || config.model_id || 'N/A',
      baseUrl: config.openAiBaseUrl || config.ollamaBaseUrl || config.base_url || 'N/A',
      config: item.config
    });
  }

  // 添加工作区级配置
  for (const item of llmSettings.value.workspaceConfigs) {
    const config = item.config.config || item.config;
    providers.push({
      name: item.name,
      source: item.source,
      is_default: item.is_default,
      apiProvider: config.apiProvider || 'openai',
      modelId: config.openAiModelId || config.ollamaModelId || config.model_id || 'N/A',
      baseUrl: config.openAiBaseUrl || config.ollamaBaseUrl || config.base_url || 'N/A',
      config: item.config
    });
  }

  return providers;
});

// Mode Settings 相关
const modeSettings = ref<{
  customModes: unknown[];
  mcpServers: Record<string, unknown>;
  allModes: Array<{
    slug: string;
    name: string;
    description: string;
    is_default: boolean;
    source: 'system' | 'user' | 'workspace';
  }>;
}>({
  customModes: [],
  mcpServers: {},
  allModes: []
});

// MCP Settings 相关 (独立管理)
const mcpSettings = ref<Record<string, unknown>>({});

// Mode 管理
const showModeDialog = ref(false);
const showViewModeDialog = ref(false);
const editingMode = ref<string | null>(null);
const viewingMode = ref<unknown>(null);
const modeForm = ref({
  slug: '',
  name: '',
  description: '',
  roleDefinition: '',
  whenToUse: '',
  customInstructions: '',
  groups: []
});
const modeYamlContent = ref('');

const modeList = computed(() => {
  return modeSettings.value.allModes || [];
});

// Mode Rules 管理
const showModeRulesDialog = ref(false);
const editingModeRules = ref<unknown>(null);
const modeRulesContent = ref('');
const modeRulesPath = ref<string | null>(null);  // 规则文件的实际路径（已废弃）
const modeRulesDirectory = ref<string | null>(null);  // 规则目录路径
const modeRuleFiles = ref<Array<{ name: string, content: string }>>([]);  // 所有规则文件
const currentRuleFile = ref<{ name: string, content: string } | null>(null);  // 当前选中的文件

// MCP 服务器管理
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

const mcpServerList = computed(() => {
  return Object.entries(mcpSettings.value || {}).map(([name, config]: [string, unknown]) => ({
    name,
    ...config
  }));
});

// Plugins Settings 相关
const pluginList = ref<unknown[]>([]);
const loadingPlugins = ref(false);

watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal && props.workspaceId) {
    // 重置加载状态，确保首次打开时 tabs 在数据加载完成后才渲染
    settingsLoaded.value = false;
    // 如果有指定 initialTab，则切换到该 tab
    if (props.initialTab) {
      activeTab.value = props.initialTab;
    }
    loadSettings();
  }
});

// Watch for workspaceId changes and load settings when it becomes available
watch(() => props.workspaceId, (newWorkspaceId) => {
  if (newWorkspaceId && visible.value) {
    // 重置加载状态
    settingsLoaded.value = false;
    // 如果有指定 initialTab，则切换到该 tab
    if (props.initialTab) {
      activeTab.value = props.initialTab;
    }
    loadSettings();
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});

const loadSettings = async (forceReload: boolean = false) => {
  if (!props.workspaceId) return;
  settingsLoaded.value = false; // 开始加载时重置状态
  await Promise.all([
    loadWorkspaceInfo(),
    loadWorkspaceConfig(),
    loadUIEnvironments(),
    loadSystemEnvironments(),
    loadUIContext(),
    loadLLMSettings(),
    loadModeSettings(forceReload),
    loadMcpSettings(),
    loadAdvancedSettings(),
    loadSkills(forceReload),
    loadPlugins(forceReload),
    loadProxyConfig()  // 加载代理配置
  ]);
  settingsLoaded.value = true; // 加载完成后设置状态，确保 tabs 正确渲染
};

// 工作区配置相关方法
const loadWorkspaceInfo = async () => {
  if (!props.workspaceId) return;
  try {
    const workspaces = await apiManager.getWorkspacesApi().getWorkspaces();
    const currentWorkspace = workspaces.find(w => w.id === props.workspaceId);
    if (currentWorkspace) {
      workspaceInfo.value = {
        id: currentWorkspace.id,
        path: currentWorkspace.path,
        createdAt: currentWorkspace.created_at || '',
        lastModified: currentWorkspace.last_modified || ''
      };
    }
  } catch (error) {
    console.error('Failed to load workspace info:', error);
  }
};

const loadWorkspaceConfig = async () => {
  if (!props.workspaceId) return;
  try {
    const response = await apiManager.getWorkspacesApi().getWorkspaceConfig(props.workspaceId);
    if (response.success && response.config) {
      // 合并加载的配置和默认配置，确保所有字段都存在
      workspaceConfig.value = {
        agent: { ...workspaceConfig.value.agent, ...response.config.agent },
        checkpoint: { ...workspaceConfig.value.checkpoint, ...response.config.checkpoint },
        compression: { ...workspaceConfig.value.compression, ...response.config.compression },
        memory: { ...workspaceConfig.value.memory, ...response.config.memory },
        skills: { ...workspaceConfig.value.skills, ...response.config.skills },
        tools: { ...workspaceConfig.value.tools, ...response.config.tools },
        logging: { ...workspaceConfig.value.logging, ...response.config.logging },
        analytics: { ...workspaceConfig.value.analytics, ...response.config.analytics }
      };
    }
  } catch (error) {
    ElMessage.error(t('workspaceSettings.workspace.messages.loadFailed'));
    console.error('Failed to load workspace config:', error);
  }
};

const saveWorkspaceConfig = async () => {
  if (!props.workspaceId) return;
  saving.value = true;
  try {
    const response = await apiManager.getWorkspacesApi().updateWorkspaceConfig(props.workspaceId, workspaceConfig.value);
    if (response.success) {
      ElMessage.success(t('workspaceSettings.workspace.messages.saveSuccess'));
    }
  } catch (error) {
    ElMessage.error(t('workspaceSettings.messages.operationFailed'));
    console.error('Failed to save workspace config:', error);
  } finally {
    saving.value = false;
  }
};

const resetWorkspaceConfig = async () => {
  if (!props.workspaceId) return;
  try {
    const response = await apiManager.getWorkspacesApi().resetWorkspaceConfig(props.workspaceId);
    if (response.success && response.config) {
      workspaceConfig.value = {
        agent: { ...workspaceConfig.value.agent, ...response.config.agent },
        checkpoint: { ...workspaceConfig.value.checkpoint, ...response.config.checkpoint },
        compression: { ...workspaceConfig.value.compression, ...response.config.compression },
        memory: { ...workspaceConfig.value.memory, ...response.config.memory },
        skills: { ...workspaceConfig.value.skills, ...response.config.skills },
        tools: { ...workspaceConfig.value.tools, ...response.config.tools },
        logging: { ...workspaceConfig.value.logging, ...response.config.logging },
        analytics: { ...workspaceConfig.value.analytics, ...response.config.analytics }
      };
      ElMessage.success('配置已重置为默认值');
    }
  } catch (error) {
    ElMessage.error(t('workspaceSettings.messages.operationFailed'));
    console.error('Failed to reset workspace config:', error);
  }
};

const loadUIEnvironments = async () => {
  if (!props.workspaceId) return;
  try {
    const data = await apiManager.getWorkspacesApi().getUIEnvironments(props.workspaceId);
    uiEnvironments.value = data || {};
  } catch (error) {
    console.error('Failed to load UI environments:', error);
  }
};

const loadSystemEnvironments = async () => {
  if (!props.workspaceId) return;
  try {
    const data = await apiManager.getWorkspacesApi().getSystemEnvironments(props.workspaceId);
    systemEnvironments.value = data || {};
  } catch (error) {
    console.error('Failed to load system environments:', error);
  }
};

const loadUIContext = async () => {
  if (!props.workspaceId) return;
  try {
    await apiManager.getWorkspacesApi().getUIContext(props.workspaceId);
    // UI Context removed
  } catch (error) {
    console.error('Failed to load UI context:', error);
  }
};

// 加载代理配置
const loadProxyConfig = async () => {
  if (!props.workspaceId) return;
  try {
    const data = await apiManager.getWorkspacesApi().getProxyConfig(props.workspaceId);
    // 只提取代理字段，不包含 success、message 等额外字段
    proxyConfig.value = {
      http_proxy: data?.http_proxy || '',
      https_proxy: data?.https_proxy || '',
      no_proxy: data?.no_proxy || ''
    };
  } catch (error) {
    console.error('Failed to load proxy config:', error);
    proxyConfig.value = { http_proxy: '', https_proxy: '', no_proxy: '' };
  }
};

// 保存代理配置
const saveProxyConfig = async () => {
  if (!props.workspaceId) return;
  savingProxy.value = true;
  try {
    console.log('[Proxy] Saving config:', JSON.stringify(proxyConfig.value));
    const result = await apiManager.getWorkspacesApi().updateProxyConfig(props.workspaceId, proxyConfig.value);
    console.log('[Proxy] Save success, result:', result);

    // ✅ 更新本地状态，确保数据一致性
    proxyConfig.value = {
      http_proxy: result.http_proxy || '',
      https_proxy: result.https_proxy || '',
      no_proxy: result.no_proxy || ''
    };
    console.log('[Proxy] Local state updated:', proxyConfig.value);

    ElMessage.success(t('workspaceSettings.proxy.saveSuccess'));
  } catch (error) {
    console.error('[Proxy] Failed to save proxy config:', error);
    ElMessage.error(t('workspaceSettings.proxy.saveError'));
  } finally {
    savingProxy.value = false;
  }
};

// const saveUIContext = async () => {
//   // Removed - UI Context tab deleted
// }

const loadLLMSettings = async () => {
  if (!props.workspaceId) return;
  loading.value = true;
  try {
    // 调用新的 API 端点获取所有级别的配置
    const response = await apiManager.getWorkspacesApi().getLLMSettingsAllLevels(props.workspaceId);

    llmSettings.value.currentApiConfigName = response.settings.current_config;
    llmSettings.value.userConfigs = response.settings.user || [];
    llmSettings.value.workspaceConfigs = response.settings.workspace || [];

    // 为了兼容旧代码，构建 allConfigs（合并后的配置）
    llmSettings.value.allConfigs = {};
    for (const item of llmSettings.value.userConfigs) {
      // item.config 包含 {name, config: {...}, source, ...}
      // 真正的配置数据在 item.config.config 中
      const configData = item.config.config || item.config;
      llmSettings.value.allConfigs[item.name] = configData;
    }
    for (const item of llmSettings.value.workspaceConfigs) {
      // item.config 包含 {name, config: {...}, source, ...}
      // 真正的配置数据在 item.config.config 中
      const configData = item.config.config || item.config;
      llmSettings.value.allConfigs[item.name] = configData;
    }

    // 初始化 modeApiConfigs,如果后端没有返回则使用空值
    const modeConfigs = response.settings.mode_configs || {};
    llmSettings.value.modeApiConfigs = {
      architect: modeConfigs.architect || '',
      code: modeConfigs.code || '',
      ask: modeConfigs.ask || '',
      debug: modeConfigs.debug || '',
      orchestrator: modeConfigs.orchestrator || ''
    };
  } catch (error) {
    ElMessage.error('加载 LLM 配置失败');
    console.error('Failed to load LLM settings:', error);
  } finally {
    loading.value = false;
  }
};

// const saveLLMSettings = async () => {
//   if (!props.workspaceId) return;
//   saving.value = true;
//   try {
//     await apiManager.getWorkspacesApi().updateLLMSettings(props.workspaceId, {
//       currentApiConfigName: llmSettings.value.currentApiConfigName || undefined,
//       modeApiConfigs: llmSettings.value.modeApiConfigs
//     });
//     ElMessage.success('LLM 配置保存成功');
//   } catch {
//     ElMessage.error(t('workspaceSettings.messages.operationFailed'));
//     console.error('Failed to save LLM settings');
//   } finally {
//     saving.value = false;
//   }
// };

// Advanced Settings methods removed
const loadAdvancedSettings = async () => {
  // Removed - Advanced Settings tab deleted
};

// const saveAdvancedSettings = async () => {
//   // Removed - Advanced Settings tab deleted
//   // saveAdvancedSettings function is no longer needed
// };

const handleClose = () => {
  visible.value = false;
};

// Provider 管理方法
const showCreateProviderDialog = () => {
  editingProvider.value = null;
  providerForm.value = {
    name: '',
    apiProvider: 'openai',
    openAiBaseUrl: 'https://api.openai.com/v1',
    openAiApiKey: '',
    openAiModelId: 'gpt-4o-mini',
    openAiLegacyFormat: false,
    openAiHeaders: {},
    ollamaBaseUrl: '',
    ollamaModelId: '',
    ollamaApiKey: '',
    diffEnabled: true,
    todoListEnabled: true,
    fuzzyMatchThreshold: 1,
    rateLimitSeconds: 0,
    consecutiveMistakeLimit: 3,
    enableReasoningEffort: true,
    saveLocation: 'user' as 'user' | 'workspace'  // 默认保存到用户级
  };
  customHeadersText.value = '';
  showProviderDialog.value = true;
};

const onApiProviderChange = () => {
  // 当切换 API 类型时自动填充推荐的配置
  const provider = providerForm.value.apiProvider;

  // 提供商推荐配置
  const providerConfigs: Record<string, { baseUrl: string; modelId: string; headers?: Record<string, string> }> = {
    openai: {
      baseUrl: 'https://api.openai.com/v1',
      modelId: 'gpt-4o-mini'
    },
    deepseek: {
      baseUrl: 'https://api.deepseek.com',
      modelId: 'deepseek-chat'
    },
    moonshot: {
      baseUrl: 'https://api.moonshot.cn/v1',
      modelId: 'moonshot-v1-8k'
    },
    qwen: {
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      modelId: 'qwen-turbo'
    },
    glm: {
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      modelId: 'glm-4-flash'
    },
    gemini: {
      baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
      modelId: 'gemini-2.0-flash-exp'
    },
    claude: {
      baseUrl: 'https://api.anthropic.com/v1',
      modelId: 'claude-3-5-sonnet-20241022',
      headers: {
        'anthropic-version': '2023-06-01'
      }
    },
    minimax: {
      baseUrl: 'https://api.minimax.chat/v1',
      modelId: 'abab6.5s-chat'
    },
    openrouter: {
      baseUrl: 'https://openrouter.ai/api/v1',
      modelId: 'openai/gpt-4o'
    },
    ollama: {
      baseUrl: 'http://localhost:11434',
      modelId: 'llama3.1'
    }
  };

  const config = providerConfigs[provider];
  if (config) {
    if (provider === 'ollama') {
      // Ollama 使用不同的字段名
      providerForm.value.ollamaBaseUrl = config.baseUrl;
      providerForm.value.ollamaModelId = config.modelId;
      // 清空 OpenAI 字段
      providerForm.value.openAiBaseUrl = '';
      providerForm.value.openAiApiKey = '';
      providerForm.value.openAiModelId = '';
      providerForm.value.openAiLegacyFormat = false;
      customHeadersText.value = '';
    } else {
      // 其他提供商使用 OpenAI 兼容字段
      providerForm.value.openAiBaseUrl = config.baseUrl;
      providerForm.value.openAiModelId = config.modelId;
      // 清空 Ollama 字段
      providerForm.value.ollamaBaseUrl = '';
      providerForm.value.ollamaModelId = '';
      providerForm.value.ollamaApiKey = '';

      // 处理自定义 headers
      if (config.headers) {
        providerForm.value.openAiHeaders = config.headers;
        customHeadersText.value = JSON.stringify(config.headers, null, 2);
      } else {
        providerForm.value.openAiHeaders = {};
        customHeadersText.value = '';
      }
    }
  }
};

const viewProvider = (provider: unknown) => {
  viewingProvider.value = provider;
  showViewProviderDialog.value = true;
};

const editProvider = (provider: unknown) => {
  editingProvider.value = provider.name;
  const config = llmSettings.value.allConfigs[provider.name];

  providerForm.value = {
    name: provider.name,
    apiProvider: config.apiProvider,
    openAiBaseUrl: config.openAiBaseUrl || '',
    openAiApiKey: config.openAiApiKey || '',
    openAiModelId: config.openAiModelId || '',
    openAiLegacyFormat: config.openAiLegacyFormat || false,
    openAiHeaders: config.openAiHeaders || {},
    ollamaBaseUrl: config.ollamaBaseUrl || '',
    ollamaModelId: config.ollamaModelId || '',
    ollamaApiKey: config.ollamaApiKey || '',
    diffEnabled: config.diffEnabled ?? true,
    todoListEnabled: config.todoListEnabled ?? true,
    fuzzyMatchThreshold: config.fuzzyMatchThreshold ?? 1,
    rateLimitSeconds: config.rateLimitSeconds ?? 0,
    consecutiveMistakeLimit: config.consecutiveMistakeLimit ?? 3,
    enableReasoningEffort: config.enableReasoningEffort ?? true
  };

  // 序列化 headers 到文本
  customHeadersText.value = Object.keys(providerForm.value.openAiHeaders).length > 0
    ? JSON.stringify(providerForm.value.openAiHeaders, null, 2)
    : '';

  showProviderDialog.value = true;
  // Reset test result
  providerTestResult.value = null;
};

// Test provider Tool Call support
const testProvider = async () => {
  if (!props.workspaceId) return;
  if (!providerForm.value.openAiModelId && providerForm.value.apiProvider !== 'ollama') {
    ElMessage.error('请填写模型 ID');
    return;
  }
  if (providerForm.value.apiProvider === 'ollama' && !providerForm.value.ollamaModelId) {
    ElMessage.error('请填写模型 ID');
    return;
  }

  testingProvider.value = true;
  providerTestResult.value = null;

  try {
    // 解析自定义 Headers
    let headers: Record<string, string> = {};
    if (customHeadersText.value.trim()) {
      try {
        headers = JSON.parse(customHeadersText.value);
      } catch {
        ElMessage.error('自定义 Headers 格式错误，请输入有效的 JSON');
        testingProvider.value = false;
        return;
      }
    }

    const providerData = {
      ...providerForm.value,
      openAiHeaders: headers
    };

    const response = await apiManager.getWorkspacesApi().testLLMProvider(
      props.workspaceId,
      providerData
    );

    providerTestResult.value = response;

    if (response.supported) {
      ElMessage.success(response.message || '测试通过');
    } else {
      ElMessage.warning(response.message || '测试失败');
    }
  } catch (error: unknown) {
    const errMsg = error.response?.data?.detail || error.message || '测试失败';
    ElMessage.error(errMsg);
    providerTestResult.value = {
      success: false,
      supported: false,
      message: errMsg
    };
  } finally {
    testingProvider.value = false;
  }
};

const saveProvider = async () => {
  if (!props.workspaceId) return;
  if (!providerForm.value.name) {
    ElMessage.error('请输入 Provider 名称');
    return;
  }

  saving.value = true;
  try {
    // 解析自定义 Headers
    let headers: Record<string, string> = {};
    if (customHeadersText.value.trim()) {
      try {
        headers = JSON.parse(customHeadersText.value);
        if (typeof headers !== 'object' || headers === null) {
          throw new Error('Headers 必须是对象');
        }
      } catch {
        ElMessage.error('自定义 Headers 格式错误，请输入有效的 JSON');
        return;
      }
    }

    // 准备保存的数据
    const providerData = {
      ...providerForm.value,
      openAiHeaders: headers
    };

    if (editingProvider.value) {
      // 更新现有 Provider（编辑时不包含 saveLocation）
      const { saveLocation, ...updateData } = providerData;
      await apiManager.getWorkspacesApi().updateLLMProvider(
        props.workspaceId,
        editingProvider.value,
        updateData
      );
      ElMessage.success('Provider 更新成功');
    } else {
      // 创建新 Provider（包含 saveLocation）
      await apiManager.getWorkspacesApi().createLLMProvider(
        props.workspaceId,
        providerData
      );
      ElMessage.success('Provider 创建成功');
    }

    showProviderDialog.value = false;
    await loadLLMSettings(); // 重新加载配置
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || '操作失败');
    console.error('Failed to save provider:', error);
  } finally {
    saving.value = false;
  }
};

const deleteProvider = async (providerName: string) => {
  if (!props.workspaceId) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除 Provider "${providerName}" 吗?此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    saving.value = true;
    await apiManager.getWorkspacesApi().deleteLLMProvider(props.workspaceId, providerName);
    ElMessage.success('Provider 删除成功');
    await loadLLMSettings(); // 重新加载配置
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败');
      console.error('Failed to delete provider:', error);
    }
  } finally {
    saving.value = false;
  }
};

// ==================== Mode Settings 管理方法 ====================

const loadModeSettings = async (forceReload: boolean = false) => {
  if (!props.workspaceId) return;
  try {
    // 获取所有模式（包括内置和自定义）
    // forceReload: 是否强制重新加载（绕过缓存）
    const response = await apiManager.getWorkspacesApi().getModes(props.workspaceId, forceReload);
    modeSettings.value.allModes = response.modes || [];

    // 保留 customModes 用于兼容旧代码
    modeSettings.value.customModes = response.modes?.filter((m: unknown) => m.source !== 'system') || [];
  } catch (error) {
    ElMessage.error('加载 Mode 设置失败');
    console.error('Failed to load mode settings:', error);
  }
};

const loadMcpSettings = async () => {
  if (!props.workspaceId) return;
  try {
    const response = await apiManager.getWorkspacesApi().getModeSettings(props.workspaceId);
    mcpSettings.value = response.settings.mcpServers || {};
  } catch (error) {
    ElMessage.error('加载 MCP 设置失败');
    console.error('Failed to load MCP settings:', error);
  }
};

// Mode 管理
const showCreateModeDialog = () => {
  editingMode.value = null;
  modeForm.value = {
    slug: '',
    name: '',
    description: '',
    roleDefinition: '',
    whenToUse: '',
    customInstructions: '',
    groups: []
  };
  showModeDialog.value = true;
};

const viewModel = (mode: unknown) => {
  viewingMode.value = mode;
  showViewModeDialog.value = true;
};

const editMode = (mode: unknown) => {
  editingMode.value = mode.slug;
  modeForm.value = { ...mode };

  // 将模式配置转换为 YAML 格式
  const modeConfig = {
    slug: mode.slug,
    name: mode.name,
    description: mode.description,
    roleDefinition: mode.role_definition || mode.roleDefinition || '',
    whenToUse: mode.when_to_use || mode.whenToUse || '',
    customInstructions: mode.custom_instructions || mode.customInstructions || '',
    groups: mode.groups || []
  };

  try {
    modeYamlContent.value = yaml.dump(modeConfig, {
      indent: 2,
      lineWidth: -1,  // 不限制行宽
      noRefs: true,    // 不使用引用
      sortKeys: false  // 保持原始顺序
    });
  } catch (error) {
    console.error('Failed to convert mode to YAML:', error);
    modeYamlContent.value = '# Error converting mode to YAML\n' + JSON.stringify(modeConfig, null, 2);
  }

  showModeDialog.value = true;
};

const saveMode = async () => {
  if (!props.workspaceId) return;

  saving.value = true;
  try {
    if (editingMode.value) {
      // 编辑模式：从 YAML 解析配置
      try {
        const parsedConfig = yaml.load(modeYamlContent.value) as Record<string, unknown>;

        // 验证必需字段
        if (!parsedConfig.slug || !parsedConfig.name || !parsedConfig.description) {
          ElMessage.warning('YAML 配置缺少必需字段 (slug, name, description)');
          return;
        }

        await apiManager.getWorkspacesApi().updateMode(
          props.workspaceId,
          editingMode.value,
          parsedConfig
        );
        ElMessage.success('模式更新成功');
      } catch (error) {
        ElMessage.error('YAML 解析失败: ' + (error as Error).message);
        console.error('Failed to parse YAML:', error);
        return;
      }
    } else {
      // 创建模式：使用表单数据
      if (!modeForm.value.slug || !modeForm.value.name || !modeForm.value.description) {
        ElMessage.warning('请填写必填字段');
        return;
      }

      await apiManager.getWorkspacesApi().createMode(
        props.workspaceId,
        modeForm.value
      );
      ElMessage.success('模式创建成功');
    }

    showModeDialog.value = false;
    await loadModeSettings();
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || '操作失败');
    console.error('Failed to save mode:', error);
  } finally {
    saving.value = false;
  }
};

const deleteMode = async (modeSlug: string) => {
  if (!props.workspaceId) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除模式 "${modeSlug}" 吗?此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    saving.value = true;

    // 执行删除
    await apiManager.getWorkspacesApi().deleteMode(props.workspaceId, modeSlug);

    // 清空本地模式列表以确保重新加载
    modeSettings.value.allModes = [];
    modeSettings.value.customModes = [];

    // 添加短暂延迟确保文件系统操作完成
    await new Promise(resolve => setTimeout(resolve, 300));

    // 强制重新加载模式列表（绕过缓存）
    await loadModeSettings(true);

    ElMessage.success('模式删除成功');
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败');
      console.error('Failed to delete mode:', error);
      // 失败时也重新加载列表以确保状态一致
      await loadModeSettings(true);
    }
  } finally {
    saving.value = false;
  }
};

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

// Mode Rules 管理
const editModeRules = async (mode: unknown) => {
  if (!props.workspaceId) return;

  editingModeRules.value = mode;
  modeRulesContent.value = '';
  modeRulesPath.value = null;  // 重置路径

  saving.value = true;
  try {
    const response = await apiManager.getWorkspacesApi().getModeRules(props.workspaceId, mode.slug);
    // response.rules 现在是一个字典 (Record<string, string>)
    // 将字典转换为数组供 UI 使用
    modeRuleFiles.value = Object.entries(response.rules || {}).map(([name, content]) => ({ name, content }));
    modeRulesDirectory.value = response.directory || null;  // 修复：使用正确的变量名

    // 如果有规则文件，默认选中第一个
    if (modeRuleFiles.value.length > 0) {
      currentRuleFile.value = modeRuleFiles.value[0];
    }

    showModeRulesDialog.value = true;

    // 初始化 Vditor
    await nextTick();
    initRulesVditor();
  } catch {
    // 如果 rules 文件不存在，使用空内容
    modeRuleFiles.value = [];
    currentRuleFile.value = null;
    modeRulesDirectory.value = null;  // 修复：使用正确的变量名
    showModeRulesDialog.value = true;

    // 初始化 Vditor
    await nextTick();
    initRulesVditor();
  } finally {
    saving.value = false;
  }
};

const saveModeRules = async () => {
  if (!props.workspaceId || !editingModeRules.value) return;

  saving.value = true;
  try {
    // 从 Vditor 获取当前编辑的文件内容
    const currentContent = rulesVditor.value ? rulesVditor.value.getValue() : '';

    // 更新当前文件的内容
    if (currentRuleFile.value) {
      currentRuleFile.value.content = currentContent;
    }

    // 将 modeRuleFiles 数组转换为字典
    const rulesDict: Record<string, string> = {};
    modeRuleFiles.value.forEach(file => {
      rulesDict[file.name] = file.content;
    });

    await apiManager.getWorkspacesApi().updateModeRules(
      props.workspaceId,
      editingModeRules.value.slug,
      rulesDict  // 传递字典而不是字符串
    );
    ElMessage.success('Rules 保存成功');
    showModeRulesDialog.value = false;
    // 立即刷新模式列表,使更改生效
    await loadModeSettings(true);
  } catch (error: unknown) {
    ElMessage.error('保存 Rules 失败: ' + (error.message || '未知错误'));
  } finally {
    saving.value = false;
  }
};

// Vditor 初始化函数
const initRulesVditor = () => {
  if (!rulesVditorRef.value) return;

  // 获取当前文件内容
  const currentContent = currentRuleFile.value?.content || '';

  // 如果已经初始化过，只更新值
  if (rulesVditorInitialized.value && rulesVditor.value) {
    const currentValue = rulesVditor.value.getValue();
    if (currentValue !== currentContent) {
      rulesVditor.value.setValue(currentContent);
    }
    return;
  }

  // 首次初始化 - 使用 value 参数而不是在 after 中调用 setValue
  rulesVditor.value = new Vditor(rulesVditorRef.value, {
    theme: themeStore.theme === 'dark' ? 'dark' : 'classic',
    mode: 'wysiwyg',
    height: 500,
    value: currentContent,  // 直接在初始化时传入值，避免 lute 未初始化问题
    placeholder: '输入该模式的 rules 内容...',
    cache: {
      enable: false,
    },
    input: (value: string) => {
      // 更新当前文件的内容
      if (currentRuleFile.value) {
        currentRuleFile.value.content = value;
      }
    },
    after: () => {
      rulesVditorInitialized.value = true;
    },
  });
};

// 选择规则文件
const selectRuleFile = (file: { name: string; content: string }) => {
  currentRuleFile.value = file;
  if (rulesVditorInitialized.value && rulesVditor.value) {
    rulesVditor.value.setValue(file.content);
  }
};

// 添加新规则文件
const addNewRuleFile = () => {
  const fileName = prompt('请输入新规则文件的名称（将自动添加 .md 扩展名）:');
  if (fileName && fileName.trim()) {
    // 自动添加 .md 扩展名（如果用户没有输入）
    let finalFileName = fileName.trim();
    if (!finalFileName.endsWith('.md')) {
      finalFileName = finalFileName + '.md';
    }
    const newFile = { name: finalFileName, content: '# New Rules\n\nAdd your rules here.' };
    modeRuleFiles.value.push(newFile);
    currentRuleFile.value = newFile;
    if (rulesVditorInitialized.value && rulesVditor.value) {
      rulesVditor.value.setValue(newFile.content);
    }
  }
};

// 删除规则文件
const deleteRuleFile = (fileName: string) => {
  if (modeRuleFiles.value.length <= 1) {
    ElMessage.warning('至少需要保留一个规则文件');
    return;
  }

  ElMessageBox.confirm(`确定要删除规则文件 "${fileName}" 吗？`, '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    const index = modeRuleFiles.value.findIndex(f => f.name === fileName);
    if (index > -1) {
      modeRuleFiles.value.splice(index, 1);
      // 如果删除的是当前文件，选中第一个
      if (currentRuleFile.value?.name === fileName) {
        currentRuleFile.value = modeRuleFiles.value[0] || null;
        if (rulesVditorInitialized.value && rulesVditor.value && currentRuleFile.value) {
          rulesVditor.value.setValue(currentRuleFile.value.content);
        }
      }
      ElMessage.success('删除成功');
    }
  }).catch(() => {
    // 用户取消
  });
};

// 监听主题变化
watch(() => themeStore.theme, (newTheme) => {
  rulesVditor.value?.setTheme(newTheme === 'dark' ? 'dark' : 'classic');
});

const resetModeRulesForm = () => {
  editingModeRules.value = null;
  modeRulesContent.value = '';
  modeRuleFiles.value = [];
  currentRuleFile.value = null;
  rulesVditorInitialized.value = false;
  if (rulesVditor.value) {
    rulesVditor.value.destroy();
    rulesVditor.value = null;
  }
};

// MCP 服务器管理
const showCreateMcpDialog = () => {
  editingMcpServer.value = null;
  mcpForm.value = {
    name: '',
    command: '',
    argsText: '',
    cwd: '',
    timeout: 300,
    alwaysAllowText: ''
  };
  showMcpDialog.value = true;
};

const editMcpServer = (server: unknown) => {
  editingMcpServer.value = server.name;
  mcpForm.value = {
    name: server.name,
    command: server.command,
    argsText: (server.args || []).join(' '),
    cwd: server.cwd || '',
    timeout: server.timeout || 300,
    alwaysAllowText: (server.alwaysAllow || []).join(', ')
  };
  showMcpDialog.value = true;
};

const saveMcpServer = async () => {
  if (!props.workspaceId) return;

  if (!mcpForm.value.name || !mcpForm.value.command) {
    ElMessage.warning('请填写服务器名称和启动命令');
    return;
  }

  saving.value = true;
  try {
    // 解析参数
    const args = mcpForm.value.argsText
      .split(/\s+/)
      .filter(arg => arg.trim().length > 0);

    const alwaysAllow = mcpForm.value.alwaysAllowText
      .split(/[,\s]+/)
      .filter(arg => arg.trim().length > 0);

    const serverConfig = {
      command: mcpForm.value.command,
      args,
      cwd: mcpForm.value.cwd || undefined,
      timeout: mcpForm.value.timeout || undefined,
      alwaysAllow: alwaysAllow.length > 0 ? alwaysAllow : undefined
    };

    // 更新 MCP servers
    const updatedServers = { ...mcpSettings.value };
    if (editingMcpServer.value) {
      updatedServers[mcpForm.value.name] = serverConfig;
    } else {
      if (updatedServers[mcpForm.value.name]) {
        ElMessage.warning('服务器名称已存在');
        return;
      }
      updatedServers[mcpForm.value.name] = serverConfig;
    }

    await apiManager.getWorkspacesApi().updateMcpSettings(
      props.workspaceId,
      { mcpServers: updatedServers }
    );

    ElMessage.success(editingMcpServer.value ? 'MCP 服务器更新成功' : 'MCP 服务器创建成功');
    showMcpDialog.value = false;
    await loadMcpSettings();
  } catch (error: unknown) {
    ElMessage.error(error.response?.data?.detail || '操作失败');
    console.error('Failed to save MCP server:', error);
  } finally {
    saving.value = false;
  }
};

const deleteMcpServer = async (serverName: string) => {
  if (!props.workspaceId) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除 MCP 服务器 "${serverName}" 吗?`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    saving.value = true;
    const updatedServers = { ...mcpSettings.value };
    delete updatedServers[serverName];

    await apiManager.getWorkspacesApi().updateMcpSettings(
      props.workspaceId,
      { mcpServers: updatedServers }
    );

    ElMessage.success('MCP 服务器删除成功');
    await loadMcpSettings();
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败');
      console.error('Failed to delete MCP server:', error);
    }
  } finally {
    saving.value = false;
  }
};

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

// ==================== Skills 管理方法 ====================

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
const skillVditorRef = ref<HTMLDivElement | null>(null);
const skillVditor = ref<Vditor | null>(null);
const skillVditorInitialized = ref(false);
const savingSkillFile = ref(false);

// 代理配置
const proxyConfig = ref({
  http_proxy: '',
  https_proxy: '',
  no_proxy: ''
});
const savingProxy = ref(false);

// 过滤后的 skills 列表
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

const loadSkills = async (forceReload: boolean = false) => {
  if (!props.workspaceId) {
    ElMessage.warning(t('workspaceSettings.messages.selectWorkspace'));
    return;
  }

  loadingSkills.value = true;
  try {
    const response = await apiManager.getSkillsApi().listSkills({
      workspace_id: props.workspaceId,
      force_reload: forceReload
    });
    skillsList.value = response.skills || [];
    ElMessage.success(t('workspaceSettings.skills.skillsLoaded', { count: skillsList.value.length }));
  } catch (error) {
    ElMessage.error(t('workspaceSettings.messages.loadingFailed'));
    console.error('Failed to load skills:', error);
  } finally {
    loadingSkills.value = false;
  }
};

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

  // 获取技能的完整内容
  try {
    const contentResponse = await skillsApi.getSkillContent(skill.name, {
      workspace_id: props.workspaceId
    });
    editSkillForm.value.content = contentResponse.content || '';
    editSkillDialogVisible.value = true;
  } catch (error) {
    ElMessage.error(t('workspaceSettings.skills.messages.loadContentFailed'));
    console.error('Failed to load skill content:', error);
  }
};

// 保存技能
const saveSkill = async () => {
  if (!currentEditingSkill.value || !props.workspaceId) {
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
      { workspace_id: props.workspaceId }
    );
    ElMessage.success(t('workspaceSettings.skills.messages.saveSuccess'));
    editSkillDialogVisible.value = false;
    // 重新加载技能列表
    await loadSkills();
  } catch (error) {
    ElMessage.error(t('workspaceSettings.skills.messages.saveFailed'));
    console.error('Failed to save skill:', error);
  } finally {
    savingSkill.value = false;
  }
};

// 删除技能
const deleteSkill = async (skill: Skill) => {
  if (!props.workspaceId) {
    return;
  }

  try {
    const response = await skillsApi.deleteSkill(skill.name, {
      workspace_id: props.workspaceId
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
      ElMessage.success(t('workspaceSettings.skills.messages.deleteSuccess'));
    }
  } catch (error) {
    ElMessage.error(t('workspaceSettings.skills.messages.deleteFailed'));
    console.error('Failed to delete skill:', error);
    // 失败时也重新加载列表以确保状态一致
    await loadSkills();
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
  if (!createSkillForm.value.name || !props.workspaceId) {
    ElMessage.warning(t('workspaceSettings.skills.messages.createNeedWorkspace'));
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
      { workspace_id: props.workspaceId }
    );
    ElMessage.success(t('workspaceSettings.skills.messages.createSuccess'));
    createSkillDialogVisible.value = false;
    // 重新加载技能列表
    await loadSkills();
  } catch (error) {
    ElMessage.error(t('workspaceSettings.skills.messages.createFailed'));
    console.error('Failed to create skill:', error);
  } finally {
    creatingSkill.value = false;
  }
};

// ==================== 技能文件编辑器相关方法 ====================

// 初始化技能编辑器 Vditor
const initSkillVditor = (initialContent: string = '') => {
  // 如果已初始化，先销毁
  if (skillVditor.value) {
    skillVditor.value.destroy();
    skillVditor.value = null;
  }

  // 确保 ref 元素存在
  if (!skillVditorRef.value) {
    console.error('Vditor ref element not found');
    return;
  }

  skillVditor.value = new Vditor(skillVditorRef.value, {
    theme: themeStore.theme === 'dark' ? 'dark' : 'classic',
    mode: 'wysiwyg',
    height: '100%',
    value: initialContent,
    placeholder: '输入文件内容...',
    cache: {
      enable: false,
    },
    input: (value: string) => {
      // 实时更新内容到当前文件对象
      if (currentSkillFile.value) {
        currentSkillFile.value.content = value;
      }
    },
    after: () => {
      skillVditorInitialized.value = true;
    }
  });
};

// 打开技能编辑器对话框
const openSkillEditorDialog = async (skill: Skill) => {
  editingSkill.value = skill;
  showSkillEditorDialog.value = true;
  skillFileTree.value = [];
  currentSkillFile.value = null;

  // 加载文件树
  await loadSkillFileTree();
};

// 加载技能文件树
const loadSkillFileTree = async () => {
  if (!editingSkill.value) return;

  skillFileTreeLoading.value = true;
  try {
    const response = await skillsApi.getSkillFileTree(editingSkill.value.name, {
      workspace_id: props.workspaceId || undefined
    });
    skillFileTree.value = response.tree || [];

    // 默认选中 SKILL.md 文件
    const skillFile = skillFileTree.value.find(item => item.name === 'SKILL.md');
    if (skillFile) {
      await handleSkillFileClick(skillFile);
    }
  } catch (error) {
    console.error('Failed to load skill file tree:', error);
    ElMessage.error(t('workspaceSettings.skills.editor.loadTreeFailed'));
  } finally {
    skillFileTreeLoading.value = false;
  }
};

// 刷新技能文件树
const refreshSkillFileTree = async () => {
  await loadSkillFileTree();
};

// 处理文件点击
const handleSkillFileClick = async (file: SkillFileTreeItem) => {
  if (file.type === 'folder') return;

  currentSkillFile.value = file;

  // 加载文件内容
  if (!editingSkill.value) return;

  try {
    const response = await skillsApi.getSkillFileContent(
      editingSkill.value.name,
      file.path,
      { workspace_id: props.workspaceId || undefined }
    );

    // 等待 DOM 更新让元素渲染
    await nextTick();
    await new Promise(resolve => setTimeout(resolve, 50));

    // 初始化或更新 Vditor
    if (!skillVditor.value) {
      initSkillVditor(response.content);
    } else {
      skillVditor.value.setValue(response.content);
    }
  } catch (error) {
    console.error('Failed to load file content:', error);
    ElMessage.error(t('workspaceSettings.skills.editor.loadContentFailed'));
  }
};

// 保存当前文件
const saveSkillFile = async () => {
  if (!editingSkill.value || !currentSkillFile.value || !skillVditor.value) return;

  savingSkillFile.value = true;
  try {
    const content = skillVditor.value.getValue();
    await skillsApi.updateSkillFileContent(
      editingSkill.value.name,
      currentSkillFile.value.path,
      content,
      { workspace_id: props.workspaceId || undefined }
    );
    ElMessage.success(t('workspaceSettings.skills.editor.saveSuccess'));
  } catch (error) {
    console.error('Failed to save file:', error);
    ElMessage.error(t('workspaceSettings.skills.editor.saveFailed'));
  } finally {
    savingSkillFile.value = false;
  }
};

// 关闭技能编辑器对话框
const closeSkillEditorDialog = () => {
  // 销毁 Vditor 实例
  if (skillVditor.value) {
    skillVditor.value.destroy();
    skillVditor.value = null;
    skillVditorInitialized.value = false;
  }

  showSkillEditorDialog.value = false;
  editingSkill.value = null;
  skillFileTree.value = [];
  currentSkillFile.value = null;
};

// ==================== Scope 辅助函数 ====================

// Scope 显示名称映射
const scopeDisplayNames: Record<string, string> = {
  workspace: '工作区',
  system: '系统',
  user: '用户'
};

// Scope 标签类型映射
const scopeTagTypes: Record<string, 'warning' | 'success' | 'info'> = {
  workspace: 'warning',
  system: 'info',
  user: 'success'
};

const getScopeDisplayName = (scope: string) => {
  return scopeDisplayNames[scope] || scope;
};

const getScopeTagType = (scope: string) => {
  return scopeTagTypes[scope] || 'info';
};

// ==================== Provider 辅助函数 ====================

// 提供商显示名称映射
const providerDisplayNames: Record<string, string> = {
  openai: 'OpenAI兼容',
  deepseek: 'DeepSeek',
  moonshot: 'Moonshot (Kimi)',
  qwen: 'Qwen (通义千问)',
  glm: 'GLM (智谱)',
  gemini: 'Gemini',
  claude: 'Claude',
  minimax: 'MiniMax',
  openrouter: 'OpenRouter',
  ollama: 'Ollama (本地)'
};

// 判断是否为 Ollama Provider
const isOllamaProvider = (provider: string): boolean => {
  return provider === 'ollama';
};

// 获取 Provider 分隔标题
const getProviderDividerTitle = (provider: string): string => {
  const titles: Record<string, string> = {
    openai: 'OpenAI兼容 配置',
    deepseek: 'DeepSeek 配置',
    moonshot: 'Moonshot 配置',
    qwen: 'Qwen 配置',
    glm: 'GLM 配置',
    gemini: 'Gemini 配置',
    claude: 'Claude 配置',
    minimax: 'MiniMax 配置',
    openrouter: 'OpenRouter 配置',
    ollama: 'Ollama 配置'
  };
  return titles[provider] || 'API 配置';
};

// 提供商标签类型映射
const providerTagTypes: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
  openai: 'primary',
  deepseek: 'success',
  moonshot: 'success',
  qwen: 'success',
  glm: 'success',
  gemini: 'warning',
  claude: 'danger',
  minimax: 'info',
  openrouter: 'primary',
  ollama: 'info'
};

const getProviderDisplayName = (provider: string) => {
  return providerDisplayNames[provider] || provider;
};

const getProviderTagType = (provider: string) => {
  return providerTagTypes[provider] || 'info';
};

// ==================== Market Dialog 方法 ====================

const openMarketDialog = (type: ResourceType) => {
  if (!props.workspaceId) {
    ElMessage.warning(t('workspaceSettings.messages.selectWorkspace'));
    return;
  }
  marketResourceType.value = type;
  marketDialogVisible.value = true;
};

/**
 * 处理资源安装成功事件
 * 根据资源类型立即刷新对应的列表,并调用后端API重新加载配置
 */
const handleResourceInstalled = async (type: ResourceType) => {
  if (!props.workspaceId) {
    return;
  }

  try {
    // 调用后端 API 重新加载配置
    const workspacesApi = apiManager.getWorkspacesApi();
    const result = await workspacesApi.reloadWorkspaceConfig(
      props.workspaceId,
      type === 'plugin' ? 'tools' : type,  // plugin 对应 tools 配置
      true  // 强制重新加载
    );

    if (result.success) {
      console.log('[WorkspaceSettings] Config reload result:', result);
    }
  } catch (error) {
    console.error('[WorkspaceSettings] Failed to reload config:', error);
    // 即使重新加载失败,也继续刷新前端列表
  }

  // 根据安装的资源类型,刷新对应的列表
  switch (type) {
    case 'skill':
      // 立即刷新技能列表
      await loadSkills(true);
      break;
    case 'agent':
      // 立即刷新智能体列表
      await loadModeSettings(true);
      break;
    case 'plugin':
      // 立即刷新插件列表
      await loadPlugins(true);
      break;
  }

  // 显示提示消息
  const typeNames = {
    skill: '技能',
    agent: '智能体',
    plugin: '插件'
  };
  ElMessage.success(`${typeNames[type]}已安装并立即生效`);
};

// ==================== Plugins 管理方法 ====================

const handlePrivacyConfigChanged = (config: unknown) => {
  if (workspaceConfig.value.analytics) {
    workspaceConfig.value.analytics = config as typeof workspaceConfig.value.analytics;
  }
};

const loadPlugins = async (forceReload: boolean = false) => {
  if (!props.workspaceId) {
    ElMessage.warning(t('workspaceSettings.messages.selectWorkspace'));
    return;
  }

  loadingPlugins.value = true;
  try {
    // Use plugins API instead of market API
    const { pluginsApi } = await import('@/services/api/plugins');
    const plugins = await pluginsApi.listPlugins(props.workspaceId, forceReload);

    // Transform plugins to match expected format
    pluginList.value = plugins.map(plugin => ({
      name: plugin.name,
      version: plugin.version,
      description: plugin.description,
      install_path: `Plugin ID: ${plugin.id}`,
      installed_at: plugin.enabled ? new Date().toISOString() : 'N/A',
      id: plugin.id,
      enabled: plugin.enabled,
      activated: plugin.activated,
      type: plugin.type
    }));

    ElMessage.success(t('workspaceSettings.plugins.pluginsLoaded', { count: pluginList.value.length }));
  } catch (error) {
    ElMessage.error(t('workspaceSettings.plugins.loadFailed'));
    console.error('Failed to load plugins:', error);
  } finally {
    loadingPlugins.value = false;
  }
};

// 组件卸载时清理 Vditor 实例
onUnmounted(() => {
  if (rulesVditor.value) {
    rulesVditor.value.destroy();
    rulesVditor.value = null;
  }
  if (skillVditor.value) {
    skillVditor.value.destroy();
    skillVditor.value = null;
  }
});
</script>

<style scoped>
.workspace-settings-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.workspace-settings-drawer :deep(.el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-title {
  font-size: 18px;
  font-weight: 600;
}

.drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.settings-form {
  padding: 16px;
}

.provider-management {
  padding: 16px;
}

.provider-header {
  margin-bottom: 16px;
}

.mode-settings {
  padding: 16px;
}

.mcp-settings {
  padding: 16px;
}

.skills-settings {
  padding: 16px;
}

.plugins-settings {
  padding: 16px;
}

.environment-sub-tabs {
  background: transparent;
  margin-bottom: 16px;
}

.environment-sub-tabs :deep(.el-tabs__header) {
  margin: 0;
  background: var(--el-bg-color);
  border-radius: 4px;
  padding: 8px;
}

.environment-sub-tabs :deep(.el-tabs__nav) {
  border: none;
}

.environment-sub-tabs :deep(.el-tabs__item) {
  border: none;
  padding: 0 16px;
  height: 32px;
  line-height: 32px;
  margin: 0 4px;
  border-radius: 4px;
  transition: all 0.3s;
}

.environment-sub-tabs :deep(.el-tabs__item:hover) {
  background: var(--el-fill-color-light);
}

.environment-sub-tabs :deep(.el-tabs__item.is-active) {
  background: var(--el-color-primary);
  color: white;
}

.environment-sub-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.workspace-config {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.workspace-form {
  padding-bottom: 40px;
}

.workspace-form :deep(.el-divider) {
  margin: 24px 0 16px 0;
  font-weight: 600;
}

.workspace-form :deep(.el-divider__text) {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.workspace-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.workspace-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.workspace-form :deep(.el-input-number) {
  width: 100%;
}

.workspace-form :deep(.el-slider) {
  width: 90%;
}

.workspace-form :deep(.el-select) {
  width: 100%;
}

.workspace-sub-tabs {
  background: transparent;
}

.workspace-sub-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px 0;
  background: var(--el-bg-color);
  border-radius: 4px;
  padding: 8px;
}

.workspace-sub-tabs :deep(.el-tabs__nav) {
  border: none;
}

.workspace-sub-tabs :deep(.el-tabs__item) {
  border: none;
  padding: 0 16px;
  height: 32px;
  line-height: 32px;
  margin: 0 4px;
  border-radius: 4px;
  transition: all 0.3s;
}

.workspace-sub-tabs :deep(.el-tabs__item:hover) {
  background: var(--el-fill-color-light);
}

.workspace-sub-tabs :deep(.el-tabs__item.is-active) {
  background: var(--el-color-primary);
  color: white;
}

.workspace-sub-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

/* Rule file item styling */
.rule-file-item {
  border-bottom: 1px solid var(--el-border-color);
  transition: background-color 0.2s;
}

.rule-file-item:hover {
  background-color: var(--el-fill-color-light);
}

.rule-file-item.active {
  background-color: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}

.rule-file-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
  display: inline-block;
}

/* Rules editor Vditor 样式 */
.rules-editor-container {
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

.rules-editor-container :deep(.vditor) {
  border: none;
}

.rules-editor-container :deep(.vditor-toolbar) {
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-bg-color);
}

.rules-editor-container :deep(.vditor-content) {
  background-color: var(--el-bg-color);
}

/* Skill editor Vditor 样式 */
.skill-editor-container {
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
}

.skill-editor-container :deep(.vditor) {
  border: none;
}

.skill-editor-container :deep(.vditor-toolbar) {
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-bg-color);
}

.skill-editor-container :deep(.vditor-content) {
  background-color: var(--el-bg-color);
}
</style>
